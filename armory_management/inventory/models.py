# inventory/models.py
from django.db import models
import segno
import uuid

class Regiment(models.Model):
    regiment_id = models.CharField(max_length=2, primary_key=True,)
    regiment_type = models.CharField(max_length=30, unique=True, choices=[
        ('Танк', 'Танкын Баталион'),
        ('Артилери', 'Артилерийн Дивизион'),
        ('Мотобуудлага', 'Мотобуудлагын Баталион'),
    ])

class Personnel(models.Model):
    id_number = models.CharField(max_length=3, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    rank = models.CharField(max_length=20, choices=[
        ('Б/ч', 'Байлдагч'),
        ('А/б', 'Ахлах Байлдагч'),
        ('Д/т', 'Дэд Түрүүч'),
        ('Т/ч', 'Түрүүч'),
        ('А/т', 'Ахлах Түрүүч'),
    ], default='Б/ч')
    regiment = models.ForeignKey(Regiment,
                                 on_delete=models.PROTECT,
                                 related_name='personnel')
    face_encoding = models.BinaryField(null=True, blank=True)
    active_status = models.BooleanField(default=True, help_text="Whether this personnel is currently active in service")
    registration_date = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.rank} {self.first_name} {self.last_name} ({self.id_number})"
    
    class Meta:
        verbose_name_plural = "Personnel"
        ordering = ['last_name', 'first_name']

class Weapon(models.Model):
    serial_number = models.CharField(max_length=6, unique=True, verbose_name='Серийн дугаар')
    bolt_number = models.CharField(max_length=6, unique=True, verbose_name='Замгийн дугаар')
    case_number = models.CharField(max_length=6, unique=True, verbose_name='Хайрцаг ангийн тагны дугаар')
    weapon_model = models.CharField(max_length=10, choices=[
        ('АКМ', 'Автомат'),
        ('АКС', 'Автомат'),
        ('СВД', ''),
        ('ПКТ', ''),
    ])
    qr_code = models.CharField(max_length=200, unique=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=[
        ('available', 'Available'),
        ('assigned', 'Assigned'),
        ('maintenance', 'In Maintenance'),
        ('decommissioned', 'Decommissioned'),
    ], default='available')
    assigned_to = models.OneToOneField(
        Personnel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_weapon'
    )
    acquisition_date = models.DateField(null=True, blank=True)
    last_maintenance_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    LOCATION_CHOICES = [
        ('in', 'Хадгалагдасан'),
        ('out', 'Гарсан'),
    ]
    location = models.CharField(
        max_length=10,
        choices=LOCATION_CHOICES,
        default='in',
        help_text="Галт зэвсгийн байршил"
    )
    
    def __str__(self):
        return f"{self.weapon_model} - {self.serial_number}"
    
    def save(self, *args, **kwargs):
        if not self.qr_code:
            unique_id = str(uuid.uuid4()).replace('-', '')
            self.qr_code = f"WPN-{self.serial_number}-{unique_id[:12]}"

        # Update status based on assignment
        if self.assigned_to:
            self.status = 'assigned'
        elif self.status == 'assigned':
            # If no longer assigned but status wasn't manually changed
            self.status = 'available'
        
        super().save(*args, **kwargs)

    def generate_qr_code_image(self):
        if self.qr_code:
            return segno.make(self.qr_code)
        return None
