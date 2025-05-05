from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class FaceAuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'face_authentication'
    verbose_name = _('Царай танилт')

    def ready(self):
        import face_authentication.signals
