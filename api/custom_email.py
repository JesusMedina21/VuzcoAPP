from djoser import email
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from djoser.email import BaseEmailMessage


class CreateUser(email.ActivationEmail):
    template_name = 'email/users/body.html'

    def get_context_data(self):
        context = super().get_context_data()
        context.update({
            'site_name': "Vuzco",
            'domain': settings.DOMAIN,
            'protocol': settings.PROTOCOL,
            'support_email': "info@vuzco.ebiru.tech",
            'app_name': "Vuzco",
            'contact_phone': "+123456789",
        })
        return context

    def send(self, to, *args, **kwargs):
        context = self.get_context_data()
        
        # Renderiza manualmente los contenidos
        subject = render_to_string('email/users/subject.txt', context)
        subject = subject.strip()  # Elimina espacios y saltos de línea
        body_html = render_to_string('email/users/body.html', context)
        
        # Configura el correo manualmente
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
        
        # Asegúrate de que 'to' sea un string, no una lista
        if isinstance(to, (list, tuple)):
            to = to[0]  # Toma el primer elemento si es una lista
            
        email_message = EmailMultiAlternatives(
            subject=subject,
            from_email=from_email,
            to=[to]  # Aquí sí pasamos una lista
        )
        email_message.attach_alternative(body_html, "text/html")
        email_message.send()


class CustomActivationConfirmEmail(email.ActivationEmail):
    template_name = 'email/activation/body.html'  # Tu template HTML

    def get_context_data(self):
        context = super().get_context_data()
        context.update({
            'site_name': "Vuzco",
            'support_email': "info@vuzco.ebiru.tech",
            'app_name': "Vuzco",
            'contact_phone': "+123456789",
        })
        return context

    def send(self, to, *args, **kwargs):
        context = self.get_context_data()
        subject = render_to_string('email/activation/subject.txt', context).strip()
        body_html = render_to_string('email/activation/body.html', context)
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER

        if isinstance(to, (list, tuple)):
            to = to[0]

        email_message = EmailMultiAlternatives(
            subject=subject,
            from_email=from_email,
            to=[to]
        )
        email_message.attach_alternative(body_html, "text/html")
        email_message.send()

class CustomActivationNewEmail(email.ActivationEmail):
    template_name = 'email/activation/new_email/body.html'

    def get_context_data(self):
        context = super().get_context_data()
        context.update({
            'site_name': "Vuzco",
            'domain': settings.DOMAIN,
            'protocol': settings.PROTOCOL,
            'support_email': "info@vuzco.ebiru.tech",
            'app_name': "Vuzco",
            'contact_phone': "+123456789",
            'new_email': self.context.get('new_email', ''),
            'email': self.context.get('new_email', '')  # Añade esto para usar {{ email }} en tu template
        
        })
        return context

    def send(self, to, *args, **kwargs):
        context = self.get_context_data()
        
        subject = render_to_string('email/activation/new_email/subject.txt', context)
        subject = subject.strip()
        body_html = render_to_string(self.template_name, context)
        body_text = render_to_string('email/activation/new_email/body.html', context)  # Añade versión de texto plano
        
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
        
        if isinstance(to, (list, tuple)):
            to = to[0]
            
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=body_text,  # Añade el cuerpo de texto plano
            from_email=from_email,
            to=[to]
        )
        email_message.attach_alternative(body_html, "text/html")
        email_message.send()

class CustomUsernameResetEmail(email.UsernameResetEmail):
    template_name = 'email/email_reset/body.html'

    def get_context_data(self):
        context = super().get_context_data()
        context.update({
            'site_name': "Vuzco",
            'domain': settings.DOMAIN,
            'protocol': settings.PROTOCOL,
            'support_email': "info@vuzco.ebiru.tech",
            'app_name': "Vuzco",
            'contact_phone': "+123456789",
        })
        return context

    def send(self, to, *args, **kwargs):
        context = self.get_context_data()
        
        # Renderiza manualmente los contenidos
        subject = render_to_string('email/email_reset/subject.txt', context)
        subject = subject.strip()  # Elimina espacios y saltos de línea
        body_html = render_to_string('email/email_reset/body.html', context)
        
        # Configura el correo manualmente
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
        
        # Asegúrate de que 'to' sea un string, no una lista
        if isinstance(to, (list, tuple)):
            to = to[0]  # Toma el primer elemento si es una lista
            
        email_message = EmailMultiAlternatives(
            subject=subject,
            from_email=from_email,
            to=[to]  # Aquí sí pasamos una lista
        )
        email_message.attach_alternative(body_html, "text/html")
        email_message.send()


class CustomEmailReset(email.ActivationEmail):
    template_name = "email/email_reset/confirm/body.html"

    def get_context_data(self):
        context = super().get_context_data()
        context.update({
            'site_name': "Vuzco",
            'domain': settings.DOMAIN,
            'protocol': settings.PROTOCOL,
            'support_email': "info@vuzco.ebiru.tech",
            'app_name': "Vuzco",
            'contact_phone': "+123456789",
            'activation_url': f"{context['protocol']}://{context['domain']}/confirm-email/{context['uid']}/{context['token']}/"
        })
        return context

    def send(self, to, *args, **kwargs):
        context = self.get_context_data()
        
        # Renderiza manualmente los contenidos
        subject = render_to_string('email/email_reset/confirm/subject.txt', context)
        subject = subject.strip()  # Elimina espacios y saltos de línea
        body_html = render_to_string(self.template_name, context)
        body_text = render_to_string('email/email_reset/confirm/body.html', context)
        
        # Configura el correo manualmente
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
        
        # Asegúrate de que 'to' sea un string, no una lista
        if isinstance(to, (list, tuple)):
            to = to[0]  # Toma el primer elemento si es una lista
            
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=body_text,  # Versión en texto plano
            from_email=from_email,
            to=[to]  # Aquí sí pasamos una lista
        )
        email_message.attach_alternative(body_html, "text/html")  # Versión HTML
        email_message.send()



class CustomOldEmailNotification(email.ActivationEmail):
    template_name = "email/email_old/body.html"

    def get_context_data(self):
        context = super().get_context_data()
        context.update({
            'site_name': "Vuzco",
            'domain': settings.DOMAIN,
            'protocol': settings.PROTOCOL,
            'support_email': "info@vuzco.ebiru.tech",
            'app_name': "Vuzco",
            'contact_phone': "+123456789",
            'new_email': self.context.get('new_email', ''),
            'old_email': self.context.get('old_email', '')
        })
        return context

    def send(self, to, *args, **kwargs):
        context = self.get_context_data()
        
        # Renderiza los contenidos
        subject = render_to_string('email/email_old/subject.txt', context)
        subject = subject.strip()
        body_html = render_to_string(self.template_name, context)
        body_text = render_to_string('email/email_old/body.html', context)
        
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
        
        if isinstance(to, (list, tuple)):
            to = to[0]
            
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=body_text,
            from_email=from_email,
            to=[to]
        )
        email_message.attach_alternative(body_html, "text/html")
        email_message.send()

class CustomPasswordResetEmail(email.PasswordResetEmail):
    template_name = 'email/password_reset/body.html'

    def get_context_data(self):
        context = super().get_context_data()
        context.update({
            'site_name': "Vuzco",
            'domain': settings.DOMAIN,
            'protocol': settings.PROTOCOL,
            'support_email': "info@vuzco.ebiru.tech",
            'app_name': "Vuzco",
            'contact_phone': "+123456789",
        })
        return context

    def send(self, to, *args, **kwargs):
        context = self.get_context_data()
        
        # Renderiza manualmente los contenidos
        subject = render_to_string('email/password_reset/subject.txt', context)
        subject = subject.strip()  # Elimina espacios y saltos de línea
        body_html = render_to_string('email/password_reset/body.html', context)
        
        # Configura el correo manualmente
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
        
        # Asegúrate de que 'to' sea un string, no una lista
        if isinstance(to, (list, tuple)):
            to = to[0]  # Toma el primer elemento si es una lista
            
        email_message = EmailMultiAlternatives(
            subject=subject,
            from_email=from_email,
            to=[to]  # Aquí sí pasamos una lista
        )
        email_message.attach_alternative(body_html, "text/html")
        email_message.send()


class CustomPasswordConfirmEmail(email.PasswordChangedConfirmationEmail):
    template_name = 'email/password_confirm/body.html'

    def get_context_data(self):
        context = super().get_context_data()
        context.update({
            'site_name': "Vuzco",
            'domain': settings.DOMAIN,
            'protocol': settings.PROTOCOL,
            'support_email': "info@vuzco.ebiru.tech",
            'app_name': "Vuzco",
            'contact_phone': "+123456789",
        })
        return context

    def send(self, to, *args, **kwargs):
        context = self.get_context_data()
        
        subject = render_to_string('email/password_confirm/subject.txt', context)
        subject = subject.strip()
        body_html = render_to_string('email/password_confirm/body.html', context)
        
        from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
        
        if isinstance(to, (list, tuple)):
            to = to[0]
            
        email_message = EmailMultiAlternatives(
            subject=subject,
            from_email=from_email,
            to=[to]
        )
        email_message.attach_alternative(body_html, "text/html")
        email_message.send()
