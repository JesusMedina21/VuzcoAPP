import json
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from .models import ChatMessage


def get_user_model_safe():
    from django.contrib.auth import get_user_model
    return get_user_model()


def build_chat_group_name(user_a: str, user_b: str) -> str:
    ids = sorted([str(user_a), str(user_b)])
    return f'chat_{ids[0]}_{ids[1]}'


class ChatConsumer(WebsocketConsumer):
    def connect(self):
        self.receptor_id = self.scope['url_route']['kwargs']['receptor_id']
        self.user = self.scope.get('user')

        if not self.user or isinstance(self.user, AnonymousUser) or self.user.is_anonymous:
            self.close()
            return

        if str(self.user.id) == str(self.receptor_id):
            self.close()
            return

        User = get_user_model_safe()
        self.receptor = User.objects.filter(id=self.receptor_id).first()
        if not self.receptor:
            self.close()
            return

        self.room_group_name = build_chat_group_name(self.user.id, self.receptor_id)

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get('message')
        if not message:
            return

        ChatMessage.objects.create(
            emisor=self.user,
            receptor=self.receptor,
            mensaje_texto=message
        )

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'chat.message',
                'message': message,
                'emisor': str(self.user.id),
                'receptor': str(self.receptor_id),
                'hora_mensaje': timezone.now().isoformat()
            }
        )

    def chat_message(self, event):
        self.send(text_data=json.dumps({
            'message': event['message'],
            'emisor': event['emisor'],
            'receptor': event['receptor'],
            'hora_mensaje': event['hora_mensaje']
        }))
            