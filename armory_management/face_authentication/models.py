# face_authentication/models.py
from django.db import models
from inventory.models import Personnel, Weapon
from django.utils import timezone
from django.conf import settings
import os
import uuid

class WeaponTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('checkout', 'Check Out'),
        ('checkin', 'Check In'),
        ('reassign', 'Reassignment'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    personnel = models.ForeignKey(
        Personnel, 
        on_delete=models.CASCADE, 
        related_name='transactions'
    )
    weapon = models.ForeignKey(
        Weapon,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    timestamp = models.DateTimeField(default=timezone.now)
    face_confidence_score = models.FloatField(null=True, blank=True)
    verified_by = models.CharField(max_length=100, blank=True, null=True, 
                                  help_text="Admin user who verified this transaction")
    notes = models.TextField(blank=True, null=True)
    auth_log = models.ForeignKey('AuthenticationLog', on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"{self.get_transaction_type_display()}: {self.weapon} - {self.personnel} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Weapon Transaction"
        verbose_name_plural = "Weapon Transactions"

    def save(self, *args, **kwargs):
        # Get the current assignment to verify it doesn't change for checkin/checkout
        original_assignemnt = None
        if self.weapon.pk and (self.transaction_type in ['checkin', 'checkout']):
            original_assignemnt = Weapon.objects.get(pk=self.weapon.pk).assigned_to

        # Only 'reassign' transactions should update weapon assignment
        if self.transaction_type == 'reassign':
            # Update the weapon's assigned personnel
            self.weapon.assigned_to = self.pesronnel
            self.weapon.save()
    
        # Save the transaction
        super().save(*args, **kwargs)

        # Verify assignment didn't change if this was a checkin/checkout
        if original_assignemnt is not None:
            current_assignment = Weapon.objects.get(pk=self.weapon.pk).assigned_to
            if original_assignemnt != current_assignment:
                raise ValueError(f"Weapon assignment changed during {self.transaction_type} operation. This should not happen!")

class FaceRegistrationLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='face_registrations')
    timestamp = models.DateTimeField(auto_now_add=True)
    registration_time = models.DateTimeField(auto_now_add=True)  # for backward compatibility
    registered_by = models.CharField(max_length=100, blank=True, null=True)
    successful = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Face Registration: {self.personnel} ({'Success' if self.successful else 'Failed'}) - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    class Meta:
        ordering = ['-timestamp']

class FaceRecord(models.Model):
    """Model to store face recognition data"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    personnel_id = models.CharField(max_length=20, unique=True)
    face_embedding = models.BinaryField(null=True, blank=True)
    face_image_path = models.CharField(max_length=255, blank=True)
    registration_date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Face Record: {self.personnel_id}"
    
    def save_face_image(self, image_data):
        """Save face image to disk and update the path"""
        # Create directory if it doesn't exist
        face_dir = os.path.join(settings.MEDIA_ROOT, 'face_images')
        os.makedirs(face_dir, exist_ok=True)
        
        # Generate filename
        filename = f"{self.personnel_id}_{uuid.uuid4().hex}.jpg"
        filepath = os.path.join(face_dir, filename)
        
        # Save image
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        # Update path
        self.face_image_path = os.path.join('face_images', filename)
        self.save(update_fields=['face_image_path'])

class AuthenticationLog(models.Model):
    """Model to log face authentication attempts"""
    RESULT_CHOICES = [
        ('SUCCESS', 'Success'),
        ('FAILURE', 'Failure'),
        ('ERROR', 'Error'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    personnel_id = models.CharField(max_length=20, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    confidence_score = models.FloatField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_info = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    
    def __str__(self):
        return f"Auth {self.result}: {self.personnel_id} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    
    class Meta:
        ordering = ['-timestamp']

