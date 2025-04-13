from django.contrib import admin
from django.utils.html import format_html
from django.shortcuts import redirect, render
from django.urls import path
from django.http import JsonResponse
from .models import Personnel, Weapon, Regiment
from face_authentication.face_utils import FaceRecognition
import segno
from io import BytesIO
import base64
import cv2
import numpy as np
import json
import logging
import uuid
import io
from django.utils.html import mark_safe


logger = logging.getLogger(__name__)
face_recognition = FaceRecognition()

class RegimentAdmin(admin.ModelAdmin):
    list_display = ('regiment_id', 'regiment_type')
    search_fields = ('regiment_id', 'regiment_type')


class PersonnelAdmin(admin.ModelAdmin):
    list_display = ('id_number', 'first_name', 'last_name', 'rank', 'regiment', 'active_status', 'has_face_registered', 'has_weapon')
    search_fields = ('id_number', 'first_name', 'last_name', 'rank', 'regiment')
    list_filter = ('rank', 'regiment', 'active_status')
    
    def has_face_registered(self, obj):
        return bool(obj.face_encoding)
    has_face_registered.boolean = True
    
    def has_weapon(self, obj):
        try:
            return bool(obj.assigned_weapon)
        except:
            return False
    has_weapon.boolean = True
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:personnel_id>/register-face/',
                self.admin_site.admin_view(self.register_face_view),
                name='register-face',
            ),
            path(
                'api/capture-face/',
                self.admin_site.admin_view(self.capture_face),
                name='capture-face',
            ),
        ]
        return custom_urls + urls
    
    def register_face_view(self, request, personnel_id):
        personnel = Personnel.objects.get(id=personnel_id)
        context = {
            'title': f'Register Face for {personnel}',
            'personnel': personnel,
            'opts': self.model._meta,
        }
        return render(request, 'admin/inventory/personnel/register_face.html', context)
    
    def capture_face(self, request):
        if request.method == 'POST':
            try:
                # This would capture from camera or receive uploaded image
                cap = cv2.VideoCapture(0)
                ret, frame = cap.read()
                cap.release()
                
                if not ret:
                    return JsonResponse({'success': False, 'error': 'Failed to capture camera feed'})
                
                # Process with ArcFace
                face_encoding = face_recognition.detect_and_encode_face(frame)
                
                if face_encoding is None:
                    return JsonResponse({'success': False, 'error': 'No face detected'})
                
                # Save the encoding to session for later use
                request.session['face_encoding'] = face_encoding.tolist()
                
                return JsonResponse({'success': True})
            except Exception as e:
                logger.error(f"Error capturing face: {e}")
                return JsonResponse({'success': False, 'error': str(e)})
        
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    def save_model(self, request, obj, form, change):
        if 'face_encoding' in request.session:
            face_encoding = np.array(request.session['face_encoding'])
            obj.face_encoding = face_encoding.tobytes()
            del request.session['face_encoding']
            
            # Log the face registration
            from face_authentication.models import FaceRegistrationLog
            FaceRegistrationLog.objects.create(
                personnel=obj,
                registered_by=request.user.username,
                successful=True
            )
            
        super().save_model(request, obj, form, change)

class WeaponAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'weapon_model', 'status', 'assigned_to', 'display_qr_code')
    list_filter = ('status', 'weapon_model')
    search_fields = ('serial_number', 'bolt_number', 'case_number')
    actions = ['generate_qr_code', 'reassign_weapons']

    exclude = ('qr_code',)

    readonly_fields = ('qr_code_display',)
    
    def assigned_to_display(self, obj):
        return obj.assigned_to if obj.assigned_to else "-"
    assigned_to_display.short_description = "Assigned To"
    
    def reassign_weapons(self, request, queryset):
        # This action would provide a form to reassign weapons
        # from outgoing to incoming personnel
        if 'apply' in request.POST:
            # Process the reassignment
            weapon_ids = request.POST.getlist('_selected_action')
            personnel_ids = request.POST.getlist('personnel')
            
            from face_authentication.models import WeaponTransaction
            
            for i, weapon_id in enumerate(weapon_ids):
                try:
                    weapon = Weapon.objects.get(id=weapon_id)
                    if i < len(personnel_ids) and personnel_ids[i]:
                        new_personnel = Personnel.objects.get(id=personnel_ids[i])
                        
                        # First check-in from old personnel if assigned
                        if weapon.assigned_to:
                            WeaponTransaction.objects.create(
                                weapon=weapon,
                                personnel=weapon.assigned_to,
                                transaction_type='checkin',
                                verified_by=request.user.username,
                                notes=f"Automatic check-in during reassignment to {new_personnel}"
                            )
                        
                        # Then reassign to new personnel
                        WeaponTransaction.objects.create(
                            weapon=weapon,
                            personnel=new_personnel,
                            transaction_type='reassign',
                            verified_by=request.user.username,
                            notes="Reassignment via admin action"
                        )
                        
                        # The transaction save method will update the weapon's assigned_to field
                except Exception as e:
                    logger.error(f"Error in reassignment: {e}")
            
            self.message_user(request, f"Successfully reassigned {len(weapon_ids)} weapons.")
            return None
        
    def display_qr_code(self, obj):
        if not obj.qr_code:
            return "No QR Code"

        qr = segno.make(obj.qr_code, error='H')
        buffer = io.BytesIO()
        qr.save(buffer, kind='png', scale=10, dark='#000000', light='#FFFFFF')
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return mark_safe(f'<img src="data:image/png;base64,{image_base64}" width="100" height="100" />')
    
    display_qr_code.short_description = 'QR код'

    def qr_code_display(self, obj):
        if not obj.qr_code:
            return "No QR Code"

        qr = segno.make(obj.qr_code, error='H')
        buffer = io.BytesIO()
        qr.save(buffer, kind='png', scale=10)
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return mark_safe(f'<img src="data:image/png;base64,{image_base64}" width="200" height="200" />')
    qr_code_display.short_description = 'QR code'

admin.site.register(Regiment, RegimentAdmin)
admin.site.register(Personnel, PersonnelAdmin)
admin.site.register(Weapon, WeaponAdmin)