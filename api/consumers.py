import json
import logging
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from .models import ChatMessage
from .utils import send_chat_push_notification

logger = logging.getLogger(__name__)


def get_user_model_safe():
    from django.contrib.auth import get_user_model
    return get_user_model()


def build_chat_group_name(user_a: str, user_b: str) -> str:
    ids = sorted([str(user_a), str(user_b)])
    return f'chat_{ids[0]}_{ids[1]}'


class ChatConsumer(WebsocketConsumer):
    def connect(self):
        print(f"WebSocket connect attempt: receptor_id={self.scope['url_route']['kwargs']['receptor_id']}")
        self.receptor_id = self.scope['url_route']['kwargs']['receptor_id']
        self.user = self.scope.get('user')
        print(f"User: {self.user}, is_authenticated: {self.user and not self.user.is_anonymous}")

        if not self.user or isinstance(self.user, AnonymousUser) or self.user.is_anonymous:
            print("Connection rejected: user not authenticated")
            self.close()
            return

        if str(self.user.id) == str(self.receptor_id):
            print("Connection rejected: user is same as receptor")
            self.close()
            return

        User = get_user_model_safe()
        self.receptor = User.objects.filter(id=self.receptor_id).first()
        print(f"Receptor found: {self.receptor}")
        if not self.receptor:
            print("Connection rejected: receptor not found")
            self.close()
            return

        self.room_group_name = build_chat_group_name(self.user.id, self.receptor_id)
        print(f"Room group: {self.room_group_name}")

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        print("WebSocket connected successfully")
        self.accept()

    def disconnect(self, close_code):
        print(f"WebSocket disconnect: close_code={close_code}")
        if hasattr(self, 'room_group_name'):
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_name,
                self.channel_name
            )
            print(f"Left group: {self.room_group_name}")
        else:
            print("No room_group_name to discard")

    def receive(self, text_data):
        print(f"Received message: {text_data}")
        text_data_json = json.loads(text_data)
        message = text_data_json.get('message')
        if not message:
            print("No message in data")
            return

        print(f"Saving message from {self.user} to {self.receptor}")
        chat_message = ChatMessage.objects.create(
            emisor=self.user,
            receptor=self.receptor,
            mensaje_texto=message
        )
        message_id = str(chat_message.id)

        print(f"Sending to group: {self.room_group_name}")
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'chat.message',
                'id': message_id,
                'message': message,
                'emisor': str(self.user.id),
                'receptor': str(self.receptor_id),
                'hora_mensaje': timezone.now().isoformat()
            }
        )

        # Enviar notificación push al receptor del mensaje
        try:
            send_chat_push_notification(
                receptor=self.receptor,
                emisor=self.user,
                message_text=message,
                message_id=message_id,
            )
        except Exception:
            logger.exception('Error sending chat push notification')

        # Send to conversations group of the receptor
        async_to_sync(self.channel_layer.group_send)(
            f'conversations_{self.receptor_id}',
            {
                'type': 'conversation.message',
                'id': message_id,
                'message': message,
                'emisor': str(self.user.id),
                'receptor': str(self.receptor_id),
                'hora_mensaje': timezone.now().isoformat()
            }
        )

    def chat_message(self, event):
        print(f"Sending message to client: {event}")
        self.send(text_data=json.dumps({
            'id': event['id'],
            'message': event['message'],
            'emisor': event['emisor'],
            'receptor': event['receptor'],
            'hora_mensaje': event['hora_mensaje'],
            'typeuser': 'emisor' if event['emisor'] == str(self.user.id) else 'receptor'
        }))
            

class ConversationConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope.get('user')
        if not self.user or isinstance(self.user, AnonymousUser) or self.user.is_anonymous:
            self.close()
            return

        self.room_group_name = f'conversations_{self.user.id}'
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_name,
                self.channel_name
            )

    def conversation_message(self, event):
        self.send(text_data=json.dumps({
            'id': event['id'],
            'message': event['message'],
            'emisor': event['emisor'],
            'receptor': event['receptor'],
            'hora_mensaje': event['hora_mensaje'],
            'typeuser': 'receptor'  # Since it's for the receptor
        }))