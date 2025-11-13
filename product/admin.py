from django.contrib import admin
from .models import Product, UploadHistory, Webhook
# Register your models here.

admin.site.register(Product)
admin.site.register(UploadHistory)
admin.site.register(Webhook)
