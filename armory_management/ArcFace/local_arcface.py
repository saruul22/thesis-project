import os
import cv2
import numpy as np
import dlib
import pickle
from pathlib import Path

class LocalArcFaceProcessor:
    """
    A class to handle local face detection and recognition using dlib.
    Note: This is a simplified version - a full ArcFace implementation would 
    require additional deep learning models.
    """
    
    def __init__(self, models_dir='models'):
        """Initialize the face processor with required models"""
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(exist_ok=True)
        
        # Load face detector
        self.detector = dlib.get_frontal_face_detector()
        
        # Load facial landmarks predictor
        landmarks_path = self.models_dir / 'shape_predictor_68_face_landmarks.dat'
        if not landmarks_path.exists():
            raise FileNotFoundError(
                f"Landmark predictor model not found at {landmarks_path}. "
                "Please download it from http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2"
            )
        self.shape_predictor = dlib.shape_predictor(str(landmarks_path))
        
        # Load face recognition model
        recognition_path = self.models_dir / 'dlib_face_recognition_resnet_model_v1.dat'
        if not recognition_path.exists():
            raise FileNotFoundError(
                f"Face recognition model not found at {recognition_path}. "
                "Please download it from http://dlib.net/files/dlib_face_recognition_resnet_model_v1.dat.bz2"
            )
        self.face_rec_model = dlib.face_recognition_model_v1(str(recognition_path))
        
        # Database for face embeddings
        self.embeddings_db_path = self.models_dir / 'face_embeddings.pkl'
        self.load_embeddings_db()
    
    def load_embeddings_db(self):
        """Load face embeddings database from disk"""
        if self.embeddings_db_path.exists():
            with open(self.embeddings_db_path, 'rb') as f:
                self.embeddings_db = pickle.load(f)
        else:
            self.embeddings_db = {}
    
    def save_embeddings_db(self):
        """Save face embeddings database to disk"""
        with open(self.embeddings_db_path, 'wb') as f:
            pickle.dump(self.embeddings_db, f)
    
    def detect_face(self, image):
        """
        Detect faces in an image
        
        Args:
            image: BGR format image (OpenCV format)
            
        Returns:
            list of dlib.rectangle representing face locations
        """
        # Convert to grayscale for detection
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = self.detector(gray)
        
        return faces
    
    def extract_embedding(self, image, face_location=None):
        """
        Extract face embedding from an image
        
        Args:
            image: BGR format image
            face_location: Optional face location (dlib.rectangle)
            
        Returns:
            numpy array of face embedding (128 dimensions)
        """
        if face_location is None:
            # Detect face if location not provided
            faces = self.detect_face(image)
            if not faces:
                return None
            face_location = faces[0]  # Use the first detected face
        
        # Get facial landmarks
        shape = self.shape_predictor(image, face_location)
        
        # Get face embedding
        face_embedding = self.face_rec_model.compute_face_descriptor(image, shape)
        
        # Convert to numpy array
        embedding_array = np.array(face_embedding)
        
        return embedding_array
    
    def register_face(self, personnel_id, image):
        """
        Register a face in the local database
        
        Args:
            personnel_id: ID of the personnel
            image: BGR format image
            
        Returns:
            bool: True if registration successful, False otherwise
        """
        faces = self.detect_face(image)
        if not faces:
            return False
        
        # Use the largest face detected
        face = max(faces, key=lambda rect: rect.width() * rect.height())
        
        # Extract face embedding
        embedding = self.extract_embedding(image, face)
        
        if embedding is None:
            return False
        
        # Store in database
        self.embeddings_db[personnel_id] = embedding
        self.save_embeddings_db()
        
        return True
    
    def verify_face(self, personnel_id, image, threshold=0.6):
        """
        Verify a face against a stored embedding
        
        Args:
            personnel_id: ID of the personnel to verify against
            image: BGR format image
            threshold: Similarity threshold (0-1, lower means more strict)
            
        Returns:
            dict: Verification result
        """
        # Check if ID exists in database
        if personnel_id not in self.embeddings_db:
            return {
                'verified': False,
                'status': 'FAILURE',
                'error': 'Personnel ID not found in database',
                'confidence': 0.0
            }
        
        # Get stored embedding
        stored_embedding = self.embeddings_db[personnel_id]
        
        # Detect face in image
        faces = self.detect_face(image)
        if not faces:
            return {
                'verified': False,
                'status': 'FAILURE',
                'error': 'No face detected in image',
                'confidence': 0.0
            }
        
        # Use the largest face detected
        face = max(faces, key=lambda rect: rect.width() * rect.height())
        
        # Extract face embedding
        new_embedding = self.extract_embedding(image, face)
        
        if new_embedding is None:
            return {
                'verified': False,
                'status': 'FAILURE',
                'error': 'Failed to extract face embedding',
                'confidence': 0.0
            }
        
        # Calculate similarity (using Euclidean distance)
        distance = np.linalg.norm(new_embedding - stored_embedding)
        
        # Convert distance to similarity score (0-1, higher is better)
        # Using a simple conversion formula - may need adjustment
        similarity = max(0, 1 - (distance / 0.6))
        
        # Determine if verification passes threshold
        is_verified = similarity >= threshold
        
        return {
            'verified': is_verified,
            'status': 'SUCCESS' if is_verified else 'FAILURE',
            'confidence': float(similarity),
            'distance': float(distance)
        }
    
    def compare_faces(self, embedding1, embedding2):
        """
        Compare two face embeddings
        
        Args:
            embedding1: First face embedding (numpy array)
            embedding2: Second face embedding (numpy array)
            
        Returns:
            dict: Comparison results with similarity score
        """
        # Calculate similarity (using Euclidean distance)
        distance = np.linalg.norm(embedding1 - embedding2)
        
        # Convert distance to similarity score (0-1, higher is better)
        similarity = max(0, 1 - (distance / 0.6))
        
        return {
            'similarity': float(similarity),
            'distance': float(distance)
        }
    
    def extract_and_save_face(self, image, output_path):
        """
        Extract the face from an image and save it to a file
        
        Args:
            image: BGR format image
            output_path: Path to save the extracted face
            
        Returns:
            bool: True if face extraction and saving successful
        """
        faces = self.detect_face(image)
        if not faces:
            return False
        
        # Use the largest face detected
        face = max(faces, key=lambda rect: rect.width() * rect.height())
        
        # Add some margin
        left = max(0, face.left() - 20)
        top = max(0, face.top() - 20)
        right = min(image.shape[1], face.right() + 20)
        bottom = min(image.shape[0], face.bottom() + 20)
        
        # Extract face region
        face_img = image[top:bottom, left:right]
        
        # Save to file
        cv2.imwrite(output_path, face_img)
        
        return True
    
    def search_face(self, image, threshold=0.6):
        """
        Search for a face in the database
        
        Args:
            image: BGR format image
            threshold: Similarity threshold
            
        Returns:
            dict: Search results with best match
        """
        if not self.embeddings_db:
            return {
                'found': False,
                'status': 'FAILURE',
                'error': 'Empty database',
                'matches': []
            }
        
        # Detect face in image
        faces = self.detect_face(image)
        if not faces:
            return {
                'found': False,
                'status': 'FAILURE',
                'error': 'No face detected in image',
                'matches': []
            }
        
        # Use the largest face detected
        face = max(faces, key=lambda rect: rect.width() * rect.height())
        
        # Extract face embedding
        query_embedding = self.extract_embedding(image, face)
        
        if query_embedding is None:
            return {
                'found': False,
                'status': 'FAILURE',
                'error': 'Failed to extract face embedding',
                'matches': []
            }
        
        # Compare with all stored embeddings
        matches = []
        for personnel_id, stored_embedding in self.embeddings_db.items():
            # Calculate similarity
            comparison = self.compare_faces(query_embedding, stored_embedding)
            similarity = comparison['similarity']
            
            # Add to matches if above threshold
            if similarity >= threshold:
                matches.append({
                    'personnel_id': personnel_id,
                    'similarity': similarity
                })
        
        # Sort matches by similarity (descending)
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        
        return {
            'found': len(matches) > 0,
            'status': 'SUCCESS' if matches else 'FAILURE',
            'matches': matches
        }