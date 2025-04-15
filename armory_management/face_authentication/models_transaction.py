from django.db import models
from inventory.models import Weapon, Personnel
import uuid

class WeaponTransaction(models.Model):
    """Model to track weapon check-ins and check-outs"""
    TRANSACTION_TYPES = [
        ('checkout', 'Check Out'),
        ('checkin', 'Check In'),
        ('transfer', 'Transfer'),
        ('maintenance', 'Maintenance'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    weapon = models.ForeignKey(Weapon, on_delete=models.CASCADE, related_name='transactions')
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='weapon_transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    verified_by = models.CharField(max_length=100)  # User or system that verified the transaction
    notes = models.TextField(blank=True)
    auth_log = models.ForeignKey('AuthenticationLog', on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"{self.get_transaction_type_display()}: {self.weapon} - {self.personnel} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Weapon Transaction"
        verbose_name_plural = "Weapon Transactions"


class FaceRegistrationLog(models.Model):
    """Model to log face registration attempts"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='face_registrations')
    timestamp = models.DateTimeField(auto_now_add=True)
    registered_by = models.CharField(max_length=100)
    successful = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    def __str__(self):
        return f"Face Registration: {self.personnel} ({'Success' if self.successful else 'Failed'}) - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    class Meta:
        ordering = ['-timestamp']