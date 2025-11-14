import json
from channels.generic.websocket import AsyncWebsocketConsumer


class UploadProgressConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time upload progress updates
    """

    async def connect(self):
        """Accept WebSocket connection"""
        self.upload_id = self.scope['url_route']['kwargs']['upload_id']
        self.room_group_name = f'upload_progress_{self.upload_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Send initial connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': f'Connected to upload progress for upload {self.upload_id}'
        }))

    async def disconnect(self, close_code):
        """Leave room group on disconnect"""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Receive message from WebSocket (not used in this implementation)"""
        pass

    async def progress_update(self, event):
        """
        Receive progress update from channel layer and send to WebSocket
        """
        # Send progress update to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'progress_update',
            'upload_id': event['upload_id'],
            'status': event['status'],
            'total_records': event['total_records'],
            # 'processed_records': event['processed_records'],
            'successful_records': event['successful_records'],
            # 'failed_records': event['failed_records'],
            'progress_percentage': event['progress_percentage'],
            'message': event.get('message', ''),
        }))
