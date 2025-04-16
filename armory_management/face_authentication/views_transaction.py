from django.shortcuts import render
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import FaceRecord, AuthenticationLog, WeaponTransaction
from .arcface_client import ArcFaceClient
from inventory.models import Personnel, Weapon
import json
import logging
import base64
import uuid
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)
arcface_client = ArcFaceClient()

@api_view(['POST'])
def weapon_info(request):
    """
    Get information about a weapon and determine appropriate transaction
    """
    try:
        qr_code = request.data.get('qr_code')
        auto_detect = request.data.get('auto_detect', False)
        
        # Find the weapon by QR code
        try:
            weapon = Weapon.objects.get(qr_code=qr_code)
        except Weapon.DoesNotExist:
            return Response(
                {'error': 'Weapon not found with the provided QR code'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get weapon's current location
        location = getattr(weapon, 'location', 'unknown')

        # Determine recommended action based on location
        recommended_action = 'check_in' if location == 'field' else 'check_out'
        
        # Get weapon info
        weapon_info = {
            'id': weapon.id,
            'serial_number': weapon.serial_number,
            'model': weapon.weapon_model,
            'status': weapon.status,
            'location': location
        }
        
        # Get personnel info if assigned
        personnel_id = None
        personnel_info = None
        
        if weapon.assigned_to:
            personnel = weapon.assigned_to
            personnel_id = personnel.id_number
            personnel_info = {
                'id': personnel.id,
                'id_number': personnel.id_number,
                'name': f"{personnel.first_name} {personnel.last_name}",
                'rank': personnel.rank,
                'regiment': str(personnel.regiment),
            }
        
        return Response({
            'weapon_info': weapon_info,
            'personnel_id': personnel_id,
            'personnel_info': personnel_info,
            'recommended_action': recommended_action
        })
        
    except Exception as e:
        logger.error(f"Error retrieving weapon info: {str(e)}")
        return Response(
            {'error': f'Failed to retrieve weapon information: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
def weapon_transaction(request):
    """
    Handle weapon transaction (check-in/check-out) with face verification
    """
    try:
        # Get request data
        personnel_id = request.data.get('personnel_id')
        face_image_b64 = request.data.get('face_image')
        qr_code = request.data.get('qr_code')
        transaction_type = request.data.get('transaction_type', 'checkin')
        
        if not all([personnel_id, face_image_b64, qr_code]):
            return Response(
                {'error': 'Personnel ID, face image, and QR code are all required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get client IP and device info for logging
        ip_address = request.META.get('REMOTE_ADDR', None)
        device_info = request.META.get('HTTP_USER_AGENT', '')
        
        # 1. Find the weapon
        try:
            weapon = Weapon.objects.get(qr_code=qr_code)
        except Weapon.DoesNotExist:
            return Response(
                {'error': 'Weapon not found with the provided QR code'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 2. Find the personnel
        try:
            personnel = Personnel.objects.get(id_number=personnel_id)
        except Personnel.DoesNotExist:
            AuthenticationLog.objects.create(
                personnel_id=personnel_id,
                result='FAILURE',
                ip_address=ip_address,
                device_info=device_info,
                error_message='Personnel not found'
            )
            return Response(
                {'error': 'Personnel not found with the provided ID'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 3. Verify face
        # Remove data URL prefix if present
        if ',' in face_image_b64:
            face_image_b64 = face_image_b64.split(',')[1]
        
        face_image_data = base64.b64decode(face_image_b64)
        
        # Get face record
        try:
            face_record = FaceRecord.objects.get(personnel_id=personnel_id, is_active=True)
        except FaceRecord.DoesNotExist:
            # Log failed attempt
            AuthenticationLog.objects.create(
                personnel_id=personnel_id,
                result='FAILURE',
                ip_address=ip_address,
                device_info=device_info,
                error_message='No face record found'
            )
            
            return Response({
                'verified': False,
                'transaction_success': False,
                'message': 'No face record found for this personnel',
                'confidence': 0.0
            })
        
        # Get stored embedding
        stored_embedding = face_record.face_embedding
        
        # Verify using ArcFace
        verification_result = arcface_client.verify_identity(
            face_image_data, 
            stored_embedding,
            threshold=getattr(settings, 'FACE_SIMILARITY_THRESHOLD', 0.6)
        )
        
        # Log authentication attempt
        authentication_log = AuthenticationLog.objects.create(
            personnel_id=personnel_id,
            result=verification_result.get('status', 'ERROR'),
            confidence_score=verification_result.get('confidence', 0.0),
            ip_address=ip_address,
            device_info=device_info,
            error_message=verification_result.get('error', '')
        )
        
        if not verification_result.get('verified', False):
            # Failed face verification
            return Response({
                'verified': False,
                'transaction_success': False,
                'message': 'Face verification failed',
                'confidence': verification_result.get('confidence', 0.0)
            })
        
        # 4. Check the weapon's current location state
        # First check if the weapon has a location field
        weapon_location = getattr(weapon, 'location', None)
        
        # If location tracking is available
        if hasattr(weapon, 'location'):
            # For checkout transaction
            if transaction_type == 'check_out' and weapon.location == 'field':
                return Response({
                    'verified': True,
                    'transaction_success': False,
                    'message': 'This weapon is already checked out and not in the armory',
                    'confidence': verification_result.get('confidence', 0.0)
                })
            # For checkin transaction
            elif transaction_type == 'check_in' and weapon.location == 'armory':
                return Response({
                    'verified': True,
                    'transaction_success': False,
                    'message': 'This weapon is already checked in and in the armory',
                    'confidence': verification_result.get('confidence', 0.0)
                })
        
        # 5. Process transaction
        transaction_success = False
        message = ""
        
        try:
            # Map the transaction types to match your model's choices
            type_mapping = {
                'check_in': 'checkin',
                'check_out': 'checkout'
            }
            django_transaction_type = type_mapping.get(transaction_type, transaction_type)
            
            # Create transaction record
            transaction = WeaponTransaction(
                weapon=weapon,
                personnel=personnel,
                transaction_type=django_transaction_type,
                face_confidence_score=verification_result.get('confidence', 0.0),
                verified_by=f"System-{request.user}" if request.user.is_authenticated else "System",
                notes=f"Transaction via desktop client: {request.META.get('REMOTE_ADDR', 'Unknown IP')}",
                auth_log=authentication_log
            )
            
            # Save the transaction - our model's save method ensures it won't modify assignments
            transaction.save()
            
            # Update the weapon's location if that field exists
            if hasattr(weapon, 'location'):
                if django_transaction_type == 'checkout':
                    weapon.location = 'field'
                    weapon.save(update_fields=['location'])
                elif django_transaction_type == 'checkin':
                    weapon.location = 'armory'
                    weapon.save(update_fields=['location'])
            
            transaction_success = True
            if django_transaction_type == 'checkin':
                message = "Weapon checked in successfully"
            elif django_transaction_type == 'checkout':
                message = "Weapon checked out successfully"
            else:
                message = f"Transaction '{django_transaction_type}' completed successfully"
                
        except Exception as e:
            logger.error(f"Transaction processing error: {str(e)}")
            message = f"Transaction processing error: {str(e)}"
        
        # Return result
        return Response({
            'verified': True,
            'transaction_success': transaction_success,
            'message': message,
            'confidence': verification_result.get('confidence', 0.0),
            'transaction_type': transaction_type,
            'weapon_info': {
                'serial_number': weapon.serial_number,
                'model': weapon.weapon_model,
                'status': weapon.status,
                'location': getattr(weapon, 'location', 'unknown')
            },
            'personnel_info': {
                'id_number': personnel.id_number,
                'name': f"{personnel.first_name} {personnel.last_name}",
                'rank': personnel.rank
            }
        })
        
    except Exception as e:
        logger.error(f"Weapon transaction error: {str(e)}")
        return Response(
            {'error': f'Transaction failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )