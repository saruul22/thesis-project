# face_authentication/admin.py
from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.http import JsonResponse
from django.utils import timezone
from .models import WeaponTransaction, FaceRegistrationLog
from inventory.models import Weapon, Personnel
from .face_utils import FaceRecognition
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)
face_recognition = FaceRecognition()

@admin.register(WeaponTransaction)
class WeaponTransactionAdmin(admin.ModelAdmin):
    list_display = ('weapon', 'personnel', 'transaction_type', 'transaction_time', 'face_verified')
    list_filter = ('transaction_type', 'transaction_time')
    search_fields = ('weapon__serial_number', 'personnel__id_number', 'personnel__first_name', 'personnel__last_name')
    readonly_fields = ('face_confidence_score',)
    actions = ['process_checkin', 'process_checkout']
    
    def face_verified(self, obj):
        if obj.face_confidence_score and obj.face_confidence_score > 0.7:
            return True
        return False
    face_verified.boolean = True
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'scan-qr-code/',
                self.admin_site.admin_view(self.scan_qr_code_view),
                name='scan-qr-code',
            ),
            path(
                'verify-face/<str:qr_code>/',
                self.admin_site.admin_view(self.verify_face_view),
                name='verify-face',
            ),
            path(
                'api/process-transaction/',
                self.admin_site.admin_view(self.process_transaction),
                name='process-transaction',
            ),
        ]
        return custom_urls + urls
    
    def scan_qr_code_view(self, request):
        context = {
            'title': 'Scan Weapon QR Code',
            'opts': self.model._meta,
        }
        return render(request, 'admin/face_authentication/weapontransaction/scan_qr_code.html', context)
    
    def verify_face_view(self, request, qr_code):
        try:
            weapon = Weapon.objects.get(qr_code=qr_code)
            context = {
                'title': 'Verify Personnel Face',
                'opts': self.model._meta,
                'weapon': weapon,
            }
            return render(request, 'admin/face_authentication/weapontransaction/verify_face.html', context)
        except Weapon.DoesNotExist:
            self.message_user(request, 'Invalid QR code. Weapon not found.', level='error')
            return redirect('admin:face_authentication_weapontransaction_changelist')
    
    def process_transaction(self, request):
        if request.method == 'POST':
            try:
                weapon_qr = request.POST.get('weapon_qr')
                personnel_id = request.POST.get('personnel_id')
                transaction_type = request.POST.get('transaction_type')
                
                # Get weapon and personnel
                weapon = Weapon.objects.get(qr_code=weapon_qr)
                personnel = Personnel.objects.get(id=personnel_id)
                
                # Capture and verify face
                cap = cv2.VideoCapture(0)
                ret, frame = cap.read()
                cap.release()
                
                if not ret:
                    return JsonResponse({'success': False, 'error': 'Failed to capture camera feed'})
                
                # Get face encoding
                face_encoding = face_recognition.detect_and_encode_face(frame)
                
                if face_encoding is None:
                    return JsonResponse({'success': False, 'error': 'No face detected'})
                
                # Compare with stored encoding
                stored_encoding = np.frombuffer(personnel.face_encoding) if personnel.face_encoding else None
                if stored_encoding is None:
                    return JsonResponse({'success': False, 'error': 'No registered face found for this personnel'})
                
                confidence = face_recognition.compare_faces(stored_encoding, face_encoding)
                
                # Create transaction
                transaction = WeaponTransaction(
                    personnel=personnel,
                    weapon=weapon,
                    transaction_type=transaction_type,
                    face_confidence_score=confidence,
                    verified_by=request.user.username
                )
                transaction.save()
                
                return JsonResponse({
                    'success': True, 
                    'confidence': confidence,
                    'transaction_id': transaction.id
                })
                
            except Exception as e:
                logger.error(f"Error processing transaction: {e}")
                return JsonResponse({'success': False, 'error': str(e)})
        
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    def process_checkout(self, request, queryset):
        # This would be used for batch check-out operations
        # For now, redirect to individual scanning interface
        self.message_user(request, 'Please use the QR code scanner for checkout operations.')
        return redirect('admin:scan-qr-code')
    process_checkout.short_description = "Process checkout for selected weapons"
    
    def process_checkin(self, request, queryset):
        # Similar to checkout
        self.message_user(request, 'Please use the QR code scanner for checkin operations.')
        return redirect('admin:scan-qr-code')
    process_checkin.short_description = "Process checkin for selected weapons"
    
    def save_model(self, request, obj, form, change):
        # Record who verified this transaction
        if not obj.verified_by:
            obj.verified_by = request.user.username
        super().save_model(request, obj, form, change)

@admin.register(FaceRegistrationLog)
class FaceRegistrationLogAdmin(admin.ModelAdmin):
    list_display = ('personnel', 'registration_time', 'successful', 'registered_by')
    list_filter = ('successful', 'registration_time')
    search_fields = ('personnel__id_number', 'personnel__first_name', 'personnel__last_name')
    readonly_fields = ('personnel', 'registration_time', 'successful', 'error_message')