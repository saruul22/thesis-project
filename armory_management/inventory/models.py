# inventory/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
import segno
import uuid

class Regiment(models.Model):
    regiment_id = models.CharField(max_length=2, primary_key=True, verbose_name=_("Салбар нэгжийн дугаар"))
    regiment_type = models.CharField(max_length=30, unique=True, choices=[
        ('Танк', _('Танкын Баталион')),
        ('Артилери', _('Артилерийн Дивизион')),
        ('Мотобуудлага', _('Мотобуудлагын Баталион')),
    ], verbose_name=_("Салбар нэгж"))

    class Meta:
        verbose_name = _("Салбар нэгж")
        verbose_name_plural = _("Салбар нэгжүүд")

class Personnel(models.Model):
    id_number = models.CharField(max_length=3, unique=True, verbose_name=_("Алба хаагчийн дугаар"))
    first_name = models.CharField(max_length=100, verbose_name=_("Алба хаагчийнн нэр"))
    last_name = models.CharField(max_length=100, verbose_name=_("Алба хаагчийн овог"))
    rank = models.CharField(max_length=20, choices=[
        ('Б/ч', _('Байлдагч')),
        ('А/б', _('Ахлах Байлдагч')),
        ('Д/т', _('Дэд Түрүүч')),
        ('Т/ч', _('Түрүүч')),
        ('А/т', _('Ахлах Түрүүч')),
    ], default='Б/ч', verbose_name=_("Цол"))
    regiment = models.ForeignKey(Regiment,
                                 on_delete=models.PROTECT,
                                 related_name='personnel',
                                 verbose_name=_("Салбар нэгж"))
    face_encoding = models.BinaryField(null=True, blank=True, verbose_name=_("Царайны өгөгдөл"))
    active_status = models.BooleanField(default=True, verbose_name=_("Алба хааж байгаа төлөв"))
    registration_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Бүртгэсэн огноо"))
    
    def __str__(self):
        return f"{self.rank} {self.first_name} {self.last_name} ({self.id_number})"
    
    class Meta:
        verbose_name = _("Алба хаагч")
        verbose_name_plural = _("Алба хаагчид")
        ordering = ['last_name', 'first_name']

class Weapon(models.Model):
    serial_number = models.CharField(max_length=6, unique=True, verbose_name=_('Серийн дугаар'))
    bolt_number = models.CharField(max_length=6, unique=True, verbose_name=_('Замгийн дугаар'))
    case_number = models.CharField(max_length=6, unique=True, verbose_name=_('Хайрцаг ангийн тагны дугаар'))
    weapon_model = models.CharField(max_length=10, choices=[
        ('АКМ', _('Автомат')),
        ('АКС', _('Эвхдэг автомат')),
        ('СВД', _('Дурантай буу')),
        ('ПКТ', _('Пулемёт')),
    ], verbose_name=_("Бууны загвар"))
    qr_code = models.CharField(max_length=200, unique=True, blank=True, null=True, verbose_name=_("QR код"))
    status = models.CharField(max_length=20, choices=[
        ('available', _('Идвэхитэй')),
        ('assigned', _('Хариуцагчтай')),
        ('maintenance', _('Засварт байгаа')),
        ('decommissioned', _('Актлагдсан')),
    ], default='available', verbose_name=_("Төлөв"))
    assigned_to = models.OneToOneField(
        Personnel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_weapon',
        verbose_name=_("Хариуцагч")
    )
    acquisition_date = models.DateField(null=True, blank=True, verbose_name=_("Олгосон огноо"))
    last_maintenance_date = models.DateField(null=True, blank=True, verbose_name=_("Засварт орсон огноо"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Тэмдэглэл"))
    LOCATION_CHOICES = [
        ('in', _('Хадгалагдасан')),
        ('out', _('Гарсан')),
    ]
    location = models.CharField(
        max_length=10,
        choices=LOCATION_CHOICES,
        default='in',
        help_text="Галт зэвсгийн байршил",
        verbose_name=_('Галт зэвсгийн байршил'),
    )
    
    def __str__(self):
        return f"{self.weapon_model} - {self.serial_number}"
    
    def save(self, *args, **kwargs):
        if not self.qr_code:
            unique_id = str(uuid.uuid4()).replace('-', '')
            self.qr_code = f"WPN-{self.serial_number}-{unique_id[:12]}"

        # buund hariutsagch onooson bol 'assigned' bolno
        if self.assigned_to:
            self.status = 'assigned'
        elif self.status == 'assigned':
            # buu ezemshigchgui tohioldold tuluv n 'available' bolnl
            self.status = 'available'
        
        super().save(*args, **kwargs)

    def generate_qr_code_image(self):
        if self.qr_code:
            return segno.make(self.qr_code)
        return None
    
    class Meta:
        db_table = ''
        managed = True
        verbose_name = 'Галт зэвсэг'
        verbose_name_plural = 'Галт зэвсэг'
