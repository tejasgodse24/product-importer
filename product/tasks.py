from celery import shared_task
import boto3
import csv
import os
from django.db import transaction
from django.utils import timezone
from .models import Product, UploadHistory
from smart_open import open as smart_open
import logging

logger = logging.getLogger(__name__)


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

        # Mark as completed
        upload_record.status = 'completed'
        upload_record.completed_at = timezone.now()
        upload_record.total_records = stats['total']
        upload_record.successful_records = stats['successful']
        upload_record.failed_records = stats['failed']
        upload_record.save()

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
        return {'status': 'error', 'message': str(e)}


def process_csv_streaming(upload_record, s3_uri, transport_params):
    """
    Stream CSV from S3 and process in batches.
    Memory efficient - never loads entire file.
    """
    total_count = 0
    with smart_open(s3_uri, 'r', transport_params=transport_params) as f:
        for row in f:
            total_count += 1
            if len(row) < 5:
                break
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
                result = process_batch(batch)
                
                total_successful += result['successful']
                total_failed += result['failed']
                total_processed += result['successful'] + result['failed']

                print(f"batch {batch_num} processing done: {str(result)}")

                # Update progress
                upload_record.processed_records = total_processed
                upload_record.successful_records = total_successful
                upload_record.failed_records = total_failed
                upload_record.save()
                
                print(f"Batch {batch_num}: Processed {total_processed} records "
                           f"({total_successful} successful, {total_failed} failed)")
                
                batch = []  # Clear batch

        # Process remaining rows
        if batch:
            batch_num += 1
            result = process_batch(batch)
            
            total_successful += result['successful']
            total_failed += result['failed']
            total_processed += result['successful'] + result['failed']
            
            upload_record.processed_records = total_processed
            upload_record.successful_records = total_successful
            upload_record.failed_records = total_failed
            upload_record.save()
            
            print(f"Final batch {batch_num}: Total {total_processed} records "
                       f"({total_successful} successful, {total_failed} failed)")

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