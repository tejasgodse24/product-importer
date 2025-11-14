from celery import shared_task
import boto3
import csv
import os
from django.db import transaction
from django.utils import timezone
from .models import Product, UploadHistory, Webhook
from smart_open import open as smart_open
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
import requests
import time

logger = logging.getLogger(__name__)


def send_progress_update(upload_id, status , total_records, successful_records):
    """
    Send real-time progress update via WebSocket
    """
    channel_layer = get_channel_layer()

    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f'upload_progress_{upload_id}',
            {
                'type': 'progress_update',
                'upload_id': upload_id,
                'status': status,
                'total_records': total_records,
                # 'processed_records': upload_record.processed_records,
                'successful_records': successful_records,
                # 'failed_records': upload_record.failed_records,
                'progress_percentage': round((successful_records/total_records)*100),
                'message': f'Processing {successful_records}/{total_records} records'
            }
        )


@shared_task(bind=True, max_retries=3)
def trigger_webhook(self, event_type, payload):
    """
    Celery task to trigger webhooks for specific events.
    Sends HTTP POST requests to all active webhooks configured for the event.
    """
    try:
        # Get all active webhooks for this event type
        webhooks = Webhook.objects.filter(event_type=event_type, is_active=True)

        if not webhooks.exists():
            logger.info(f"No active webhooks configured for event: {event_type}")
            return {'status': 'success', 'message': 'No webhooks configured', 'triggered': 0}

        triggered_count = 0
        failed_count = 0

        for webhook in webhooks:
            logger.info(f"Triggering webhook {webhook.id} ({webhook.url}) for event: {event_type}")

            # Prepare payload with timestamp
            webhook_payload = {
                'event': event_type,
                'timestamp': timezone.now().isoformat(),
                **payload
            }

            # Send webhook request with retries
            for attempt in range(webhook.retry_count + 1):
                try:
                    start_time = time.time()
                    response = requests.post(
                        webhook.url,
                        json=webhook_payload,
                        headers={'Content-Type': 'application/json'},
                        timeout=30  # 30 second timeout
                    )
                    response_time = time.time() - start_time

                    # Update webhook stats
                    webhook.last_triggered_at = timezone.now()
                    webhook.last_response_code = response.status_code
                    webhook.last_response_time = round(response_time, 3)
                    webhook.save()

                    if 200 <= response.status_code < 300:
                        logger.info(f"Webhook {webhook.id} triggered successfully: {response.status_code}")
                        triggered_count += 1
                        break  # Success, no need to retry
                    else:
                        logger.warning(f"Webhook {webhook.id} returned non-success status: {response.status_code}")
                        if attempt < webhook.retry_count:
                            logger.info(f"Retrying webhook {webhook.id} (attempt {attempt + 2}/{webhook.retry_count + 1})")
                            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                        else:
                            failed_count += 1

                except requests.exceptions.Timeout:
                    logger.error(f"Webhook {webhook.id} timed out (attempt {attempt + 1}/{webhook.retry_count + 1})")
                    webhook.last_triggered_at = timezone.now()
                    webhook.last_response_code = None
                    webhook.last_response_time = None
                    webhook.save()

                    if attempt < webhook.retry_count:
                        time.sleep(2 ** attempt)
                    else:
                        failed_count += 1

                except requests.exceptions.RequestException as e:
                    logger.error(f"Webhook {webhook.id} request failed: {str(e)} (attempt {attempt + 1}/{webhook.retry_count + 1})")
                    webhook.last_triggered_at = timezone.now()
                    webhook.last_response_code = None
                    webhook.last_response_time = None
                    webhook.save()

                    if attempt < webhook.retry_count:
                        time.sleep(2 ** attempt)
                    else:
                        failed_count += 1

        return {
            'status': 'success',
            'event_type': event_type,
            'triggered': triggered_count,
            'failed': failed_count,
            'total': webhooks.count()
        }

    except Exception as e:
        logger.error(f"Error in trigger_webhook task: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}


@shared_task(bind=True)
def process_csv_file(self, upload_id, s3_file_url, file_extension):
    """
    Celery task to process uploaded CSV file from S3.
    Optimized for large files (500k+ records) with streaming and bulk upserts.
    """
    try:
        upload_record = UploadHistory.objects.get(id=upload_id)
        upload_record.status = 'processing'
        upload_record.save()

        # S3 setup
        session = boto3.Session(
            aws_access_key_id=os.getenv('AWS_S3_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_S3_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_S3_REGION_NAME')
        )
        s3_client = session.client('s3')

        bucket_name = os.getenv('AWS_S3_BUCKET')
        s3_key = s3_file_url.split(f"{bucket_name}.s3.{os.getenv('AWS_S3_REGION_NAME')}.amazonaws.com/")[1]
        s3_uri = f"s3://{bucket_name}/{s3_key}"

        transport_params = {'client': s3_client}

        # Process CSV
        if file_extension == '.csv':
            stats = process_csv_streaming(upload_record, s3_uri, transport_params)
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")

        # Update upload record
        upload_record.completed_at = timezone.now()
        upload_record.total_records = stats['total']
        upload_record.successful_records = stats['successful']
        upload_record.failed_records = stats['failed']

        # Check if there are any failed records
        if stats['failed'] > 0:
            # Mark as failed if there are any failed records
            upload_record.status = 'failed'
            upload_record.error_message = f"{stats['failed']} out of {stats['total']} records failed to process. This may be due to duplicate SKUs in the CSV file."
            upload_record.save()

            # Trigger bulk_upload_failed webhook
            trigger_webhook.delay('bulk_upload_failed', {
                'upload_id': upload_id,
                'file_name': upload_record.file_name,
                'total_records': stats['total'],
                'successful_records': stats['successful'],
                'failed_records': stats['failed'],
                'error_message': upload_record.error_message,
                'started_at': upload_record.started_at.isoformat(),
                'failed_at': upload_record.completed_at.isoformat(),
            })
        else:
            # Mark as completed only if all records processed successfully
            upload_record.status = 'completed'
            upload_record.save()

            # Trigger bulk_upload_complete webhook
            trigger_webhook.delay('bulk_upload_complete', {
                'upload_id': upload_id,
                'file_name': upload_record.file_name,
                'total_records': stats['total'],
                'successful_records': stats['successful'],
                'failed_records': stats['failed'],
                'started_at': upload_record.started_at.isoformat(),
                'completed_at': upload_record.completed_at.isoformat(),
            })

        return {
            'status': 'success',
            'total_records': stats['total'],
            'successful_records': stats['successful'],
            'failed_records': stats['failed']
        }

    except UploadHistory.DoesNotExist:
        logger.error(f"Upload record {upload_id} not found")
        return {'status': 'error', 'message': 'Upload record not found'}

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}", exc_info=True)
        upload_record = UploadHistory.objects.get(id=upload_id)
        upload_record.status = 'failed'
        upload_record.error_message = str(e)
        upload_record.completed_at = timezone.now()
        upload_record.save()

        # Trigger bulk_upload_failed webhook
        trigger_webhook.delay('bulk_upload_failed', {
            'upload_id': upload_id,
            'file_name': upload_record.file_name,
            'error_message': str(e),
            'started_at': upload_record.started_at.isoformat(),
            'failed_at': upload_record.completed_at.isoformat(),
        })

        return {'status': 'error', 'message': str(e)}


def process_csv_streaming(upload_record, s3_uri, transport_params):
    """
    Stream CSV from S3 and process in batches.
    Memory efficient - never loads entire file.
    """
    total_count = 0
    with smart_open(s3_uri, 'r', transport_params=transport_params) as f:
        for row in csv.DictReader(f):
            
            sku = str(row.get('sku', '')).strip().upper()
            name = str(row.get('name', '')).strip()
            description = row.get('description', '').strip()

            if not sku or not name or sku == 'nan' or name == 'nan':
                continue
            total_count += 1

    print(f"total_count is {total_count}")

    batch_size = get_batch_size(total_count=total_count)

    total_processed = 0
    total_successful = 0
    total_failed = 0
    batch_num = 0

    with smart_open(s3_uri, 'r', transport_params=transport_params) as f:
        reader = csv.DictReader(f)
        batch = []

        for row in reader:
            # batch.append(row)
            sku = str(row.get('sku', '')).strip().upper()
            name = str(row.get('name', '')).strip()
            description = str(row.get('desc', '') or row.get('description', '')).strip()

            if not sku or not name or sku == 'nan' or name == 'nan':
                continue

            batch.append(
                Product(
                    sku=sku,
                    name=name,
                    description=description if description != 'nan' else '',
                    is_active=True
                )
            )
            # Process when batch is full
            if len(batch) >= batch_size:
                batch_num += 1
                print(f"batch {batch_num} processing started")

                # De-duplicate batch (keep last occurrence of each SKU)
                unique_batch = {}
                for product in batch:
                    unique_batch[product.sku] = product
                deduplicated_batch = list(unique_batch.values())

                duplicates_removed = len(batch) - len(deduplicated_batch)
                if duplicates_removed > 0:
                    print(f"batch {batch_num}: Removed {duplicates_removed} duplicate SKUs")

                result = process_batch(deduplicated_batch)

                total_successful += result['successful']
                total_failed += result['failed'] + duplicates_removed
                total_processed += result['successful'] + result['failed'] + duplicates_removed

                print(f"batch {batch_num} processing done: {str(result)}")

                # Update progress
                # upload_record.processed_records = total_processed
                # upload_record.successful_records = total_successful
                # upload_record.failed_records = total_failed
                # upload_record.save()

                # Send WebSocket update
                send_progress_update(upload_record.id, upload_record.status, total_count, total_successful)
                
                print(f"Batch {batch_num}: Processed {total_processed} records "
                           f"({total_successful} successful, {total_failed} failed)")
                
                batch = []  # Clear batch

        # Process remaining rows
        if batch:
            batch_num += 1

            # De-duplicate final batch (keep last occurrence of each SKU)
            unique_batch = {}
            for product in batch:
                unique_batch[product.sku] = product
            deduplicated_batch = list(unique_batch.values())

            duplicates_removed = len(batch) - len(deduplicated_batch)
            if duplicates_removed > 0:
                print(f"Final batch {batch_num}: Removed {duplicates_removed} duplicate SKUs")

            result = process_batch(deduplicated_batch)

            total_successful += result['successful']
            total_failed += result['failed'] + duplicates_removed
            total_processed += result['successful'] + result['failed'] + duplicates_removed

            # upload_record.processed_records = total_processed
            # upload_record.successful_records = total_successful
            # upload_record.failed_records = total_failed
            # upload_record.save()

            # Send WebSocket update for final batch
            send_progress_update(upload_record.id, "completed", total_count, total_successful)

            print(f"Final batch {batch_num}: Total {total_processed} records "
                       f"({total_successful} successful, {total_failed} failed)")


    upload_record.processed_records = total_processed
    upload_record.successful_records = total_successful
    upload_record.failed_records = total_failed
    upload_record.save()
    
    return {
        'total': total_processed,
        'successful': total_successful,
        'failed': total_failed
    }


def process_batch(batch):
    """
    Process a batch using Django 4.2+ bulk_create with upsert.
    """
    products_to_upsert = batch
    
    if products_to_upsert:
        try:
            with transaction.atomic():
                Product.objects.bulk_create(
                    products_to_upsert,
                    update_conflicts=True,
                    unique_fields=['sku'],
                    update_fields=['name', 'description', 'is_active'],
                    # batch_size=50
                )
                successful = len(products_to_upsert)
                failed = 0                
        except Exception as e:
            logger.error(f"Bulk upsert error: {str(e)}", exc_info=True)
            failed = len(products_to_upsert)
            successful = 0
    
    return {
        'successful': successful,
        'failed': failed
    }

def get_batch_size(total_count):
    """
    Calculate batch size to achieve target number of batches.
    Good for progress tracking (e.g., want 100 progress updates).
    
    Args:
        total_count: Total number of records
        
    Returns:
        int: Optimal batch size
    """
    if total_count < 100:
        return total_count
    elif total_count > 100 and total_count < 1000:
        return 200
    
    # Round to nearest hundred for cleaner numbers
    batch_size = round(total_count / 100)
    
    # Cap at reasonable limits
    return batch_size