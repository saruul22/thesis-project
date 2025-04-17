from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import WeaponTransaction

@receiver(post_save, sender=WeaponTransaction)
def transaction_saved(sender, instance, created, **kwargs):
    """Handle transaction save events for real-time updates"""
    # This signal is just a placeholder - we'll use SSE for real-time updates
    # No additional code needed here since we're checking for updates in the SSE view
    pass