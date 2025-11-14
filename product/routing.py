from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/upload-progress/(?P<upload_id>\d+)/$', consumers.UploadProgressConsumer.as_asgi()),
]
