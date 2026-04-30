import logging
from django.apps import apps
from django.conf import settings
from firebase_admin import messaging

logger = logging.getLogger(__name__)


def send_chat_push_notification(receptor, emisor, message_text, message_id):
    device_model = apps.get_model(settings.FCM_DJANGO_FCMDEVICE_MODEL)
    devices = device_model.objects.filter(user=receptor, active=True)
    if not devices.exists():
        return

    sender_name = emisor.get_full_name() if hasattr(emisor, 'get_full_name') else None
    sender_name = sender_name or getattr(emisor, 'username', None) or getattr(emisor, 'email', None) or 'Nuevo mensaje'
    title = f"Nuevo mensaje de {sender_name}"
    body = message_text if len(message_text) <= 120 else f"{message_text[:117]}..."

    notification = messaging.Notification(title=title, body=body)
    data_payload = {
        'type': 'chat_message',
        'message_id': str(message_id),
        'sender_id': str(emisor.id) if emisor else '',
        'sender_name': sender_name,
        'receptor_id': str(receptor.id),
        'message': message_text,
    }

    for device in devices:
        message = messaging.Message(
            notification=notification,
            data=data_payload,
        )
        try:
            device.send_message(message)
        except Exception:
            logger.exception('Error sending FCM chat notification to device %s', device.pk)