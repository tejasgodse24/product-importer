from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
import boto3
from botocore.exceptions import ClientError
import os
from datetime import datetime
from smart_open import open as smart_open
import uuid
import json
from .models import Product, UploadHistory, Webhook


def upload_page(request):
    """Render the upload page"""
    return render(request, 'product/upload.html')


@require_http_methods(["POST"])
def upload_file(request):
    """
    Handle file upload to S3 and trigger Celery task for processing
    """
    try:
        # Check if file is present
        if 'file' not in request.FILES:
            return JsonResponse({
                'status': 'error',
                'message': 'No file provided'
            }, status=400)

        uploaded_file = request.FILES['file']

        # Validate file extension
        allowed_extensions = ['.csv', '.xlsx']
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()

        if file_extension not in allowed_extensions:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid file type. Only CSV and Excel files are allowed.'
            }, status=400)

        # Validate file size (100MB max)
        max_size = 100 * 1024 * 1024  # 100MB
        if uploaded_file.size > max_size:
            return JsonResponse({
                'status': 'error',
                'message': 'File size exceeds 100MB limit.'
            }, status=400)

        # Generate unique filename
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        original_name = os.path.splitext(uploaded_file.name)[0]
        s3_filename = f"uploads/{timestamp}_{unique_id}_{original_name}{file_extension}"

        # Upload to S3
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_S3_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_S3_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_S3_REGION_NAME')
            )

            bucket_name = os.getenv('AWS_S3_BUCKET')

            # Upload file to S3
            s3_client.upload_fileobj(
                uploaded_file,
                bucket_name,
                s3_filename,
                ExtraArgs={'ContentType': uploaded_file.content_type}
            )

            # Generate S3 URL
            s3_file_url = f"https://{bucket_name}.s3.{os.getenv('AWS_S3_REGION_NAME')}.amazonaws.com/{s3_filename}"

        except ClientError as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to upload to S3: {str(e)}'
            }, status=500)

        # Create upload history record
        upload_record = UploadHistory.objects.create(
            file_name=uploaded_file.name,
            file_path=s3_file_url,
            status='pending'
        )

        # Trigger Celery task (import here to avoid circular imports)
        try:
            from .tasks import process_csv_file
           
            task = process_csv_file.delay(upload_record.id, s3_file_url, ".csv")

            return JsonResponse({
                'status': 'success',
                'message': 'File uploaded successfully. Processing started in background.',
                'upload_id': upload_record.id,
                # 'task_id': str(task.id),
                's3_url': s3_file_url
            }, status=200)

        except Exception as e:
            # Update upload record status
            upload_record.status = 'failed'
            upload_record.error_message = f'Failed to start processing: {str(e)}'
            upload_record.save()

            return JsonResponse({
                'status': 'error',
                'message': f'File uploaded but processing failed to start: {str(e)}'
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'An unexpected error occurred: {str(e)}'
        }, status=500)


# ============= PRODUCT MANAGEMENT VIEWS =============

def product_list_page(request):
    """Render product list page with pagination"""
    return render(request, 'product/product_list.html')


def upload_history_page(request):
    """Render upload history page with upload modal"""
    return render(request, 'product/upload_history.html')


# ============= PRODUCT API VIEWS =============

@require_http_methods(["GET"])
def product_list_api(request):
    """
    API to get paginated product list
    Query params: page, page_size, search
    """
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        search = request.GET.get('search', '').strip()

        # Base queryset
        products = Product.objects.all().order_by('-created_at')

        # Search filter
        if search:
            products = products.filter(
                sku__icontains=search
            ) | products.filter(
                name__icontains=search
            ) | products.filter(
                description__icontains=search
            )

        # Pagination
        paginator = Paginator(products, page_size)
        page_obj = paginator.get_page(page)

        # Serialize products
        products_data = [{
            'id': p.id,
            'sku': p.sku,
            'name': p.name,
            'description': p.description,
            'is_active': p.is_active,
            'created_at': p.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': p.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        } for p in page_obj]

        return JsonResponse({
            'status': 'success',
            'data': products_data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            }
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def product_detail_api(request, product_id):
    """API to get single product details"""
    try:
        product = get_object_or_404(Product, id=product_id)

        return JsonResponse({
            'status': 'success',
            'data': {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'description': product.description,
                'is_active': product.is_active,
                'created_at': product.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': product.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=404)


@require_http_methods(["POST"])
def product_create_api(request):
    """API to create new product"""
    try:
        data = json.loads(request.body)

        # Validate required fields
        sku = data.get('sku', '').strip()
        name = data.get('name', '').strip()

        if not sku or not name:
            return JsonResponse({
                'status': 'error',
                'message': 'SKU and Name are required'
            }, status=400)

        # Check if SKU already exists (case-insensitive)
        if Product.objects.filter(sku__iexact=sku).exists():
            return JsonResponse({
                'status': 'error',
                'message': f'Product with SKU "{sku}" already exists'
            }, status=400)

        # Create product
        product = Product.objects.create(
            sku=sku.upper(),
            name=name,
            description=data.get('description', ''),
            is_active=data.get('is_active', True)
        )

        return JsonResponse({
            'status': 'success',
            'message': 'Product created successfully',
            'data': {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'description': product.description,
                'is_active': product.is_active,
            }
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["PUT", "PATCH"])
def product_update_api(request, product_id):
    """API to update product"""
    try:
        product = get_object_or_404(Product, id=product_id)
        data = json.loads(request.body)

        # Update fields if provided
        if 'name' in data:
            product.name = data['name'].strip()

        if 'description' in data:
            product.description = data['description'].strip()

        if 'is_active' in data:
            product.is_active = data['is_active']

        # SKU update (check for duplicates)
        if 'sku' in data:
            new_sku = data['sku'].strip().upper()
            if new_sku != product.sku:
                if Product.objects.filter(sku__iexact=new_sku).exclude(id=product_id).exists():
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Product with SKU "{new_sku}" already exists'
                    }, status=400)
                product.sku = new_sku

        product.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Product updated successfully',
            'data': {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'description': product.description,
                'is_active': product.is_active,
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["DELETE"])
def product_delete_api(request, product_id):
    """API to delete product"""
    try:
        product = get_object_or_404(Product, id=product_id)
        product_sku = product.sku
        product.delete()

        return JsonResponse({
            'status': 'success',
            'message': f'Product {product_sku} deleted successfully'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
def product_bulk_delete_api(request):
    """API to delete multiple products"""
    try:
        data = json.loads(request.body)
        product_ids = data.get('product_ids', [])

        if not product_ids:
            return JsonResponse({
                'status': 'error',
                'message': 'No products selected'
            }, status=400)

        # Get products to delete
        products = Product.objects.filter(id__in=product_ids)
        count = products.count()

        if count == 0:
            return JsonResponse({
                'status': 'error',
                'message': 'No products found with the given IDs'
            }, status=404)

        # Collect product info before deletion
        deleted_products = list(products.values('id', 'sku', 'name'))

        # Delete products
        products.delete()

        # Trigger bulk_delete_complete webhook
        from .tasks import trigger_webhook
        trigger_webhook.delay('bulk_delete_complete', {
            'deleted_count': count,
            'deleted_products': deleted_products,
            'timestamp': timezone.now().isoformat(),
        })

        return JsonResponse({
            'status': 'success',
            'message': f'{count} product(s) deleted successfully'
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


# ============= UPLOAD HISTORY API =============

@require_http_methods(["GET"])
def upload_history_api(request):
    """API to get upload history with pagination"""
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))

        # Get upload history
        uploads = UploadHistory.objects.all().order_by('-started_at')

        # Pagination
        paginator = Paginator(uploads, page_size)
        page_obj = paginator.get_page(page)

        # Serialize data
        uploads_data = [{
            'id': u.id,
            'file_name': u.file_name,
            'status': u.status,
            'total_records': u.total_records,
            'processed_records': u.processed_records,
            'successful_records': u.successful_records,
            'failed_records': u.failed_records,
            'progress_percentage': u.progress_percentage,
            'error_message': u.error_message,
            'started_at': u.started_at.strftime('%Y-%m-%d %H:%M:%S') if u.started_at else None,
            'completed_at': u.completed_at.strftime('%Y-%m-%d %H:%M:%S') if u.completed_at else None,
        } for u in page_obj]

        return JsonResponse({
            'status': 'success',
            'data': uploads_data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            }
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


# ============= WEBHOOK MANAGEMENT VIEWS =============

def webhook_page(request):
    """Render webhook management page"""
    return render(request, 'product/webhook_management.html')


@require_http_methods(["GET"])
def webhook_list_api(request):
    """API to get all webhooks with pagination"""
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))

        # Get webhooks
        webhooks = Webhook.objects.all().order_by('-created_at')

        # Pagination
        paginator = Paginator(webhooks, page_size)
        page_obj = paginator.get_page(page)

        # Serialize data
        webhooks_data = [{
            'id': w.id,
            'url': w.url,
            'event_type': w.event_type,
            'event_type_display': w.get_event_type_display(),
            'is_active': w.is_active,
            'description': w.description,
            'last_triggered_at': w.last_triggered_at.strftime('%Y-%m-%d %H:%M:%S') if w.last_triggered_at else None,
            'last_response_code': w.last_response_code,
            'last_response_time': w.last_response_time,
            'retry_count': w.retry_count,
            'created_at': w.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        } for w in page_obj]

        return JsonResponse({
            'status': 'success',
            'data': webhooks_data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            }
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
def webhook_create_api(request):
    """API to create new webhook"""
    try:
        data = json.loads(request.body)

        # Validate required fields
        url = data.get('url', '').strip()
        event_type = data.get('event_type', '').strip()

        if not url or not event_type:
            return JsonResponse({
                'status': 'error',
                'message': 'URL and Event Type are required'
            }, status=400)

        # Validate event type
        valid_events = [choice[0] for choice in Webhook.EVENT_CHOICES]
        if event_type not in valid_events:
            return JsonResponse({
                'status': 'error',
                'message': f'Invalid event type. Must be one of: {", ".join(valid_events)}'
            }, status=400)

        # Create webhook
        webhook = Webhook.objects.create(
            url=url,
            event_type=event_type,
            description=data.get('description', ''),
            is_active=data.get('is_active', True),
            retry_count=data.get('retry_count', 3)
        )

        return JsonResponse({
            'status': 'success',
            'message': 'Webhook created successfully',
            'data': {
                'id': webhook.id,
                'url': webhook.url,
                'event_type': webhook.event_type,
                'event_type_display': webhook.get_event_type_display(),
                'is_active': webhook.is_active,
                'description': webhook.description,
            }
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["PUT", "PATCH"])
def webhook_update_api(request, webhook_id):
    """API to update webhook"""
    try:
        webhook = get_object_or_404(Webhook, id=webhook_id)
        data = json.loads(request.body)

        # Update fields if provided
        if 'url' in data:
            webhook.url = data['url'].strip()

        if 'event_type' in data:
            event_type = data['event_type'].strip()
            valid_events = [choice[0] for choice in Webhook.EVENT_CHOICES]
            if event_type not in valid_events:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Invalid event type. Must be one of: {", ".join(valid_events)}'
                }, status=400)
            webhook.event_type = event_type

        if 'description' in data:
            webhook.description = data['description'].strip()

        if 'is_active' in data:
            webhook.is_active = data['is_active']

        if 'retry_count' in data:
            webhook.retry_count = int(data['retry_count'])

        webhook.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Webhook updated successfully',
            'data': {
                'id': webhook.id,
                'url': webhook.url,
                'event_type': webhook.event_type,
                'event_type_display': webhook.get_event_type_display(),
                'is_active': webhook.is_active,
                'description': webhook.description,
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["DELETE"])
def webhook_delete_api(request, webhook_id):
    """API to delete webhook"""
    try:
        webhook = get_object_or_404(Webhook, id=webhook_id)
        webhook_url = webhook.url
        webhook.delete()

        return JsonResponse({
            'status': 'success',
            'message': f'Webhook {webhook_url} deleted successfully'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
def webhook_test_api(request, webhook_id):
    """API to test webhook by sending a test request"""
    import requests
    import time

    try:
        webhook = get_object_or_404(Webhook, id=webhook_id)

        # Test payload
        test_payload = {
            'event': webhook.event_type,
            'test': True,
            'message': f'Test trigger for {webhook.get_event_type_display()}',
            'timestamp': timezone.now().isoformat(),
            'data': {
                'webhook_id': webhook.id,
                'webhook_url': webhook.url
            }
        }

        # Send webhook request
        start_time = time.time()
        try:
            response = requests.post(
                webhook.url,
                json=test_payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            response_time = time.time() - start_time

            # Update webhook stats
            webhook.last_triggered_at = timezone.now()
            webhook.last_response_code = response.status_code
            webhook.last_response_time = round(response_time, 3)
            webhook.save()

            return JsonResponse({
                'status': 'success',
                'message': 'Webhook test completed',
                'data': {
                    'response_code': response.status_code,
                    'response_time': round(response_time, 3),
                    'response_body': response.text[:500] if response.text else None,  # Limit to 500 chars
                }
            })

        except requests.exceptions.Timeout:
            webhook.last_triggered_at = timezone.now()
            webhook.last_response_code = None
            webhook.last_response_time = None
            webhook.save()

            return JsonResponse({
                'status': 'error',
                'message': 'Webhook request timed out (10s)',
                'data': {
                    'response_code': None,
                    'response_time': None,
                }
            }, status=408)

        except requests.exceptions.RequestException as e:
            webhook.last_triggered_at = timezone.now()
            webhook.last_response_code = None
            webhook.last_response_time = None
            webhook.save()

            return JsonResponse({
                'status': 'error',
                'message': f'Webhook request failed: {str(e)}',
                'data': {
                    'response_code': None,
                    'response_time': None,
                }
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
