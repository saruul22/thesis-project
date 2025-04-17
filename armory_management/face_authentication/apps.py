from django.apps import AppConfig


class FaceAuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'face_authentication'

    def ready(self):
        import face_authentication.signals
