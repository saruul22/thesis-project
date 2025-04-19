# face_authentication/admin.py
from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.http import JsonResponse
from django.utils import timezone
from .models import FaceRecord, AuthenticationLog, WeaponTransaction, FaceRegistrationLog
from inventory.models import Weapon, Personnel
from .face_utils import FaceRecognition
from django.utils.html import format_html
import cv2
import numpy as np
import logging
from unfold.admin import ModelAdmin

logger = logging.getLogger(__name__)
face_recognition = FaceRecognition()

@admin.register(FaceRecord)
class FaceRecordAdmin(ModelAdmin):
    list_display = ('personnel_id', 'has_embedding', 'face_image_display', 'registration_date', 'is_active')
    list_filter = ('is_active', 'registration_date')
    search_fields = ('personnel_id',)
    readonly_fields = ('id', 'registration_date', 'last_updated', 'face_image_display')

    def has_embedding(self, obj):
        """Indicate if embedding data exists"""
        return bool(obj.face_embedding)

    has_embedding.boolean = True
    has_embedding.short_description = 'Has Embedding'

    def face_image_display(self, obj):
        """Display the face image in the admin interface"""
        if obj.face_image_path:
            return format_html('<img src="/media/{}" widht="100" height="100" />', obj.face_image_path)
        return "No image"

    face_image_display.short_description = 'Face Image'

@admin.register(AuthenticationLog)
class AuthenticationLogAdmin(ModelAdmin):
    list_display = ('personnel_id', 'timestamp', 'result', 'confidence_score', 'ip_address')
    list_filter = ('result', 'timestamp')
    search_fields = ('personnel_id', 'ip_address')
    readonly_fields = ('id', 'timestamp', 'personnel_id', 'result', 'confidence_score',
                  'ip_address', 'device_info', 'error_message')

    def has_add_permission(self, request):
        """Disable adding logs manually"""
        return False
    
    def has_change_permission(self, request):
        """Disable editing logs"""
        return False

@admin.register(WeaponTransaction)
class WeaponTransactionAdmin(ModelAdmin):
    list_display = ('transaction_type', 'weapon', 'personnel', 'timestamp', 'verified_by')
    list_filter = ('transaction_type', 'timestamp')
    search_fields = ('weapon__serial_number', 'personnel__id_number', 'personnel__id_number', 'personnel__last_name')
    readonly_fields = ('id', 'timestamp', 'auth_log')

    fieldsets = (
        ('Transaction Details', {
            'fields': ('id', 'transaction_type', 'timestamp', 'verified_by', 'notes')
        }),
        ('Related Items', {
            'fields': ('weapon', 'personnel', 'auth_log')
        }),
    )

@admin.register(FaceRegistrationLog)
class FaceRegistrationLogAdmin(ModelAdmin):
    list_display = ('personnel', 'timestamp', 'registered_by', 'successful')
    list_filter = ('successful', 'timestamp')
    search_fields = ('personnel__id_number', 'personnel__last_name', 'registered_by')
    readonly_fields = ('id', 'timestamp', 'personnel','registered_by', 'successful', 'error_message')

    def has_add_permission(self, request):
        """Disable addmin logs automatically"""
        return False

    def has_change_permission(self, request, obj = None):
        """Disable editing logs"""
        return False
