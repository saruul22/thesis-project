from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import FaceRecord, AuthenticationLog
from .arcface_client import ArcFaceClient
from inventory.models import Personnel
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)
arcface_client = ArcFaceClient()

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_faces(request):
    """
    List all available face records.
    Used for syncing local database with server.
    """
    try:
        # Get all active face records
        face_records = FaceRecord.objects.filter(is_active=True)
        
        # Prepare response
        records = []
        for record in face_records:
            records.append({
                'personnel_id': record.personnel_id,
                'registration_date': record.registration_date.isoformat(),
                'last_updated': record.last_updated.isoformat(),
                'has_embedding': bool(record.face_embedding)
            })
        
        return Response({
            'status': 'success',
            'count': len(records),
            'records': records
        })
    
    except Exception as e:
        logger.error(f"Error listing face records: {str(e)}")
        return Response(
            {'error': f'Failed to list face records: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_face_data(request, personnel_id):
    """
    Get face embedding data for a specific personnel.
    Used for syncing local database with server.
    """
    try:
        # Get face record
        try:
            face_record = FaceRecord.objects.get(personnel_id=personnel_id, is_active=True)
        except FaceRecord.DoesNotExist:
            return Response(
                {'error': f'No face record found for personnel ID {personnel_id}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if embedding exists
        if not face_record.face_embedding:
            return Response(
                {'error': 'Face record has no embedding data'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Convert embedding to base64
        import base64
        embedding_b64 = base64.b64encode(face_record.face_embedding).decode('utf-8')
        
        # Get face image URL if available
        face_image_url = None
        if face_record.face_image_path:
            face_image_url = request.build_absolute_uri(settings.MEDIA_URL + face_record.face_image_path)
        
        # Return data
        return Response({
            'status': 'success',
            'personnel_id': face_record.personnel_id,
            'embedding': embedding_b64,
            'face_image_url': face_image_url,
            'registration_date': face_record.registration_date.isoformat(),
            'last_updated': face_record.last_updated.isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error retrieving face data: {str(e)}")
        return Response(
            {'error': f'Failed to retrieve face data: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )  # Fixed the extra parenthesis here
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_face(request):
    """
    Register a face for a personnel.
    Expects: personnel_id and face_image (base64 encoded)
    """
    try:
        # Get request data
        personnel_id = request.data.get('personnel_id')
        face_image_b64 = request.data.get('face_image')
        
        if not personnel_id or not face_image_b64:
            return Response(
                {'error': 'Personnel ID and face image are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if personnel exists
        try:
            personnel = Personnel.objects.get(id_number=personnel_id)
        except Personnel.DoesNotExist:
            logger.error(f"Personnel with ID {personnel_id} not found")
            return Response(
                {'error': f'Personnel ID not found in the system'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Decode base64 image
        import base64
        from django.core.files.base import ContentFile
        
        # Remove data URL prefix if present
        if ',' in face_image_b64:
            face_image_b64 = face_image_b64.split(',')[1]
        
        face_image_data = base64.b64decode(face_image_b64)
        
        # Extract face embeddings using ArcFace
        result = arcface_client.extract_embeddings(face_image_data)
        
        if 'error' in result or result.get('status') == 'ERROR':
            return Response(
                {'error': result.get('error', 'Failed to extract face embeddings')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the embedding bytes
        embedding_bytes = result.get('embedding_bytes')
        
        if not embedding_bytes:
            return Response(
                {'error': 'No face embedding generated'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create or update face record
        face_record, created = FaceRecord.objects.update_or_create(
            personnel_id=personnel_id,
            defaults={
                'face_embedding': embedding_bytes,
                'is_active': True
            }
        )
        
        # Save the face image
        face_record.save_face_image(face_image_data)
        
        # Update the Personnel record with the same embedding
        personnel.face_encoding = embedding_bytes
        personnel.save(update_fields=['face_encoding'])
        
        return Response({
            'status': 'success',
            'message': 'Face registered successfully',
            'face_id': str(face_record.id),
            'created': created
        })
    
    except Exception as e:
        logger.error(f"Face registration error: {str(e)}")
        return Response(
            {'error': f'Face registration failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
@api_view(['POST'])
def verify_face(request):
    """
    Verify a face against a stored record.
    Expects: personnel_id and face_image (base64 encoded)
    """
    try:
        # Get request data
        personnel_id = request.data.get('personnel_id')
        face_image_b64 = request.data.get('face_image')
        
        if not personnel_id or not face_image_b64:
            return Response(
                {'error': 'Personnel ID and face image are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get client IP and device info for logging
        ip_address = request.META.get('REMOTE_ADDR', None)
        device_info = request.META.get('HTTP_USER_AGENT', '')
        
        # Decode base64 image
        import base64
        
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
            
            return Response(
                {'error': 'No face record found for this personnel'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get stored embedding
        stored_embedding = face_record.face_embedding
        
        # Verify using ArcFace
        verification_result = arcface_client.verify_identity(
            face_image_data, 
            stored_embedding,
            threshold=getattr(settings, 'FACE_SIMILARITY_THRESHOLD', 0.6)
        )
        
        # Log authentication attempt
        AuthenticationLog.objects.create(
            personnel_id=personnel_id,
            result=verification_result.get('status', 'ERROR'),
            confidence_score=verification_result.get('confidence', 0.0),
            ip_address=ip_address,
            device_info=device_info,
            error_message=verification_result.get('error', '')
        )
        
        if verification_result.get('verified', False):
            # Successful authentication
            return Response({
                'status': 'success',
                'verified': True,
                'confidence': verification_result.get('confidence', 0.0)
            })
        else:
            # Failed authentication
            return Response({
                'status': 'failed',
                'verified': False,
                'confidence': verification_result.get('confidence', 0.0),
                'message': 'Face verification failed'
            })
    
    except Exception as e:
        logger.error(f"Face verification error: {str(e)}")
        
        # Log error
        AuthenticationLog.objects.create(
            personnel_id=personnel_id if 'personnel_id' in locals() else None,
            result='ERROR',
            ip_address=request.META.get('REMOTE_ADDR', None),
            device_info=request.META.get('HTTP_USER_AGENT', ''),
            error_message=str(e)
        )
        
        return Response(
            {'error': f'Face verification failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
