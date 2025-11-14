from django.urls import path
from product import views

urlpatterns = [
    # Pages
    path('', views.product_list_page, name='product_list_page'),
    path('upload/', views.upload_history_page, name='upload_history_page'),
    path('webhooks/', views.webhook_page, name='webhook_page'),

    # Product API endpoints
    path('api/products/', views.product_list_api, name='product_list_api'),
    path('api/products/<int:product_id>/', views.product_detail_api, name='product_detail_api'),
    path('api/products/create/', views.product_create_api, name='product_create_api'),
    path('api/products/<int:product_id>/update/', views.product_update_api, name='product_update_api'),
    path('api/products/<int:product_id>/delete/', views.product_delete_api, name='product_delete_api'),
    path('api/products/bulk-delete/', views.product_bulk_delete_api, name='product_bulk_delete_api'),

    # Upload API endpoints
    path('api/upload-file/', views.upload_file, name='upload_file'),
    path('api/upload-history/', views.upload_history_api, name='upload_history_api'),

    # Webhook API endpoints
    path('api/webhooks/', views.webhook_list_api, name='webhook_list_api'),
    path('api/webhooks/create/', views.webhook_create_api, name='webhook_create_api'),
    path('api/webhooks/<int:webhook_id>/update/', views.webhook_update_api, name='webhook_update_api'),
    path('api/webhooks/<int:webhook_id>/delete/', views.webhook_delete_api, name='webhook_delete_api'),
    path('api/webhooks/<int:webhook_id>/test/', views.webhook_test_api, name='webhook_test_api'),
]
