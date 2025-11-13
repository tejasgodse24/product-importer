from django.db import models
from django.core.exceptions import ValidationError


class Product(models.Model):
    """
    Product model for storing product information from CSV imports.
    SKU is unique and case-insensitive.
    """
    sku = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Stock Keeping Unit - unique identifier (case-insensitive)"
    )
    name = models.CharField(max_length=255, help_text="Product name")
    description = models.TextField(blank=True, null=True, help_text="Product description")
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the product is active or inactive"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def save(self, *args, **kwargs):
        """Override save to ensure SKU is stored in uppercase for case-insensitive uniqueness"""
        if self.sku:
            self.sku = self.sku.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku} - {self.name}"


class UploadHistory(models.Model):
    """
    Track CSV upload history and progress
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    file_name = models.CharField(max_length=255, help_text="Original CSV file name")
    file_path = models.CharField(max_length=500, blank=True, null=True, help_text="S3 file path")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_records = models.IntegerField(default=0, help_text="Total records in CSV")
    processed_records = models.IntegerField(default=0, help_text="Number of records processed")
    successful_records = models.IntegerField(default=0, help_text="Successfully imported records")
    failed_records = models.IntegerField(default=0, help_text="Failed to import records")
    error_message = models.TextField(blank=True, null=True, help_text="Error details if failed")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Upload History'
        verbose_name_plural = 'Upload Histories'

    def __str__(self):
        return f"{self.file_name} - {self.status} ({self.processed_records}/{self.total_records})"

    @property
    def progress_percentage(self):
        """Calculate upload progress percentage"""
        if self.total_records == 0:
            return 0
        return round((self.processed_records / self.total_records) * 100, 2)


class Webhook(models.Model):
    """
    Webhook configuration for product events
    """
    EVENT_CHOICES = [
        ('product_created', 'Product Created'),
        ('product_updated', 'Product Updated'),
        ('product_deleted', 'Product Deleted'),
        ('bulk_upload_complete', 'Bulk Upload Complete'),
        ('bulk_delete_complete', 'Bulk Delete Complete'),
    ]

    url = models.URLField(max_length=500, help_text="Webhook endpoint URL")
    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        help_text="Event that triggers this webhook"
    )
    is_active = models.BooleanField(default=True, help_text="Enable or disable webhook")
    description = models.TextField(blank=True, null=True, help_text="Webhook description")
    last_triggered_at = models.DateTimeField(blank=True, null=True)
    last_response_code = models.IntegerField(blank=True, null=True, help_text="Last HTTP response code")
    last_response_time = models.FloatField(blank=True, null=True, help_text="Last response time in seconds")
    retry_count = models.IntegerField(default=3, help_text="Number of retry attempts on failure")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Webhook'
        verbose_name_plural = 'Webhooks'

    def __str__(self):
        return f"{self.event_type} -> {self.url}"
