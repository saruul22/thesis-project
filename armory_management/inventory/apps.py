from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory'
    verbose_name = _('Зэвсэг хадгалалт')

    def ready(self):
        import django.contrib.admin as admin
        from rest_framework.authtoken.models import Token
        
        try:
            admin.site.unregister(Token)
        except admin.sites.NotRegistered:
            pass

