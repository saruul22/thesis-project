# face_authentication/models.py
from django.db import models
from inventory.models import Personnel, Weapon
from django.utils import timezone
from django.conf import settings
import os
import uuid

class WeaponTransaction(models.Model):
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
    transaction_time = models.DateTimeField(default=timezone.now)
    transaction_type = models.CharField(max_length=20, choices=[
        ('checkin', 'Check In'),
        ('checkout', 'Check Out'),
        ('reassign', 'Reassignment'),
    ])
    face_confidence_score = models.FloatField(null=True, blank=True)
    verified_by = models.CharField(max_length=100, blank=True, null=True, 
                                  help_text="Admin user who verified this transaction")
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.transaction_type} - {self.weapon} by {self.personnel} on {self.transaction_time.strftime('%Y-%m-%d %H:%M')}"
    
    class Meta:
        ordering = ['-transaction_time']
    
    def save(self, *args, **kwargs):
        # Update weapon assignment based on transaction type
        if self.transaction_type == 'checkout':
            # Ensure weapon is not already assigned to someone else
            if self.weapon.assigned_to and self.weapon.assigned_to != self.personnel:
                raise ValueError(f"Weapon is already assigned to {self.weapon.assigned_to}")
            
            self.weapon.assigned_to = self.personnel
            self.weapon.save()
            
        elif self.transaction_type == 'checkin':
            # Only remove assignment if this personnel has the weapon
            if self.weapon.assigned_to == self.personnel:
                self.weapon.assigned_to = None
                self.weapon.save()
                
        elif self.transaction_type == 'reassign':
            # Special case for reassigning weapons from one conscript to another
            self.weapon.assigned_to = self.personnel
            self.weapon.save()
        
        super().save(*args, **kwargs)

class FaceRegistrationLog(models.Model):
    personnel = models.ForeignKey(Personnel, on_delete=models.CASCADE)
    registration_time = models.DateTimeField(auto_now_add=True)
    successful = models.BooleanField(default=True)
    registered_by = models.CharField(max_length=100, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Face registration for {self.personnel} on {self.registration_time.strftime('%Y-%m-%d %H:%M')}"

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
