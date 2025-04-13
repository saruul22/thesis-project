import os
import numpy as np
import requests
import json
import base64
from io import BytesIO
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class ArcFaceClient:
    """
    Client for communicating with ArcFace face recognition API.
    This implements the ArcFace algorithm for face recognition.
    """
    
    def __init__(self, api_url=None, api_key=None):
        """
        Initialize the ArcFace client.
        
        Args:
            api_url (str): The URL of the ArcFace API service
            api_key (str): API key for authentication
        """
        self.api_url = api_url or getattr(settings, 'ARCFACE_API_URL', 'http://localhost:5000/api')
        self.api_key = api_key or getattr(settings, 'ARCFACE_API_KEY', '')
        self.headers = {
            'Content-Type': 'application/json',
            'x-api-key': self.api_key
        }
    
    def detect_face(self, image_data):
        """
        Detect faces in an image.
        
        Args:
            image_data (bytes): Raw image data
            
        Returns:
            dict: Detection results with face locations
        """
        try:
            endpoint = f"{self.api_url}/detect"
            
            # Convert image to base64
            encoded_image = base64.b64encode(image_data).decode('utf-8')
            
            payload = {
                'image': encoded_image,
                'max_faces': 1  # Typically we only need one face for authentication
            }
            
            response = requests.post(endpoint, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            return result
            
        except Exception as e:
            logger.error(f"Face detection error: {str(e)}")
            return {'error': str(e), 'status': 'ERROR'}
    
    def extract_embeddings(self, image_data):
        """
        Extract face embeddings from an image.
        
        Args:
            image_data (bytes): Raw image data
            
        Returns:
            dict: Extracted face embeddings
        """
        try:
            endpoint = f"{self.api_url}/extract_embeddings"
            
            # Convert image to base64
            encoded_image = base64.b64encode(image_data).decode('utf-8')
            
            payload = {
                'image': encoded_image
            }
            
            response = requests.post(endpoint, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # Convert embeddings from base64 to numpy array if needed
            if 'embeddings' in result and result['embeddings']:
                embedding_bytes = base64.b64decode(result['embeddings'])
                embedding_array = np.frombuffer(embedding_bytes, dtype=np.float32)
                return {
                    'status': 'SUCCESS',
                    'embedding_array': embedding_array,
                    'embedding_bytes': embedding_bytes
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Embedding extraction error: {str(e)}")
            return {'error': str(e), 'status': 'ERROR'}
    
    def compare_faces(self, source_embedding, target_embedding):
        """
        Compare two face embeddings and return similarity score.
        
        Args:
            source_embedding (bytes or numpy.ndarray): The first face embedding
            target_embedding (bytes or numpy.ndarray): The second face embedding
            
        Returns:
            dict: Comparison results with similarity score
        """
        try:
            endpoint = f"{self.api_url}/compare"
            
            # Convert numpy arrays to bytes if needed
            if isinstance(source_embedding, np.ndarray):
                source_embedding = source_embedding.tobytes()
            if isinstance(target_embedding, np.ndarray):
                target_embedding = target_embedding.tobytes()
            
            # Convert to base64
            source_b64 = base64.b64encode(source_embedding).decode('utf-8')
            target_b64 = base64.b64encode(target_embedding).decode('utf-8')
            
            payload = {
                'embedding1': source_b64,
                'embedding2': target_b64
            }
            
            response = requests.post(endpoint, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            return result
            
        except Exception as e:
            logger.error(f"Face comparison error: {str(e)}")
            return {'error': str(e), 'status': 'ERROR', 'similarity': 0.0}
    
    def verify_identity(self, image_data, stored_embedding, threshold=0.6):
        """
        Verify if a face in an image matches a stored embedding.
        
        Args:
            image_data (bytes): Raw image data
            stored_embedding (bytes): The stored face embedding to compare against
            threshold (float): Similarity threshold for authentication (0-1)
            
        Returns:
            dict: Verification results
        """
        # Extract embeddings from the new image
        extraction_result = self.extract_embeddings(image_data)
        
        if 'error' in extraction_result or extraction_result.get('status') == 'ERROR':
            return {
                'verified': False,
                'status': 'ERROR',
                'error': extraction_result.get('error', 'Failed to extract embeddings'),
                'confidence': 0.0
            }
        
        # If we successfully extracted embeddings, compare with stored embedding
        if 'embedding_bytes' in extraction_result:
            new_embedding = extraction_result['embedding_bytes']
            
            # Compare the embeddings
            comparison = self.compare_faces(new_embedding, stored_embedding)
            
            if 'error' in comparison:
                return {
                    'verified': False,
                    'status': 'ERROR',
                    'error': comparison.get('error', 'Comparison failed'),
                    'confidence': 0.0
                }
            
            # Get similarity score
            similarity = comparison.get('similarity', 0.0)
            
            # Determine if verification is successful
            is_verified = similarity >= threshold
            
            return {
                'verified': is_verified,
                'status': 'SUCCESS' if is_verified else 'FAILURE',
                'confidence': similarity
            }
        
        return {
            'verified': False,
            'status': 'ERROR',
            'error': 'No embeddings extracted',
            'confidence': 0.0
        }
    
    def extract_and_save_embedding(self, image_data, save_path=None):
        """
        Extract face embedding and optionally save it to a file.
        
        Args:
            image_data (bytes): Raw image data
            save_path (str, optional): Path to save the embedding
            
        Returns:
            dict: Result with embedding data
        """
        # Extract embeddings
        result = self.extract_embeddings(image_data)
        
        if 'error' in result or result.get('status') == 'ERROR':
            return result
        
        # If save_path is provided, save the embedding
        if save_path and 'embedding_bytes' in result:
            try:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'wb') as f:
                    f.write(result['embedding_bytes'])
                result['saved'] = True
                result['save_path'] = save_path
            except Exception as e:
                logger.error(f"Error saving embedding: {str(e)}")
                result['saved'] = False
                result['save_error'] = str(e)
        
        return result
    
    def search_face(self, image_data, embeddings_dict, threshold=0.6):
        """
        Search for a face in a dictionary of embeddings.
        
        Args:
            image_data (bytes): Raw image data
            embeddings_dict (dict): Dictionary mapping IDs to embeddings
            threshold (float): Similarity threshold
            
        Returns:
            dict: Search results with best matches
        """
        # Extract embedding from the query image
        extraction_result = self.extract_embeddings(image_data)
        
        if 'error' in extraction_result or extraction_result.get('status') == 'ERROR':
            return {
                'found': False,
                'status': 'ERROR',
                'error': extraction_result.get('error', 'Failed to extract embeddings'),
                'matches': []
            }
        
        if 'embedding_bytes' not in extraction_result:
            return {
                'found': False,
                'status': 'ERROR',
                'error': 'No face embedding extracted',
                'matches': []
            }
        
        query_embedding = extraction_result['embedding_bytes']
        
        # Compare with all stored embeddings
        matches = []
        
        for person_id, stored_embedding in embeddings_dict.items():
            comparison = self.compare_faces(query_embedding, stored_embedding)
            
            if 'error' in comparison:
                continue
            
            similarity = comparison.get('similarity', 0.0)
            
            if similarity >= threshold:
                matches.append({
                    'id': person_id,
                    'similarity': similarity
                })
        
        # Sort matches by similarity (highest first)
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        
        return {
            'found': len(matches) > 0,
            'status': 'SUCCESS' if matches else 'FAILURE',
            'matches': matches
        }
    
    @classmethod
    def mock_client(cls):
        """
        Create a mock client for testing when ArcFace API is not available.
        This implements a very basic face recognition simulation.
        
        Returns:
            ArcFaceClient: A mock client instance
        """
        client = cls()
        
        # Override methods with mock implementations
        client.extract_embeddings = cls._mock_extract_embeddings
        client.compare_faces = cls._mock_compare_faces
        client.verify_identity = cls._mock_verify_identity
        
        return client
    
    @staticmethod
    def _mock_extract_embeddings(image_data):
        """Mock implementation of extract_embeddings"""
        # Generate a random embedding (128-dimensional vector)
        embedding_array = np.random.rand(128).astype(np.float32)
        embedding_bytes = embedding_array.tobytes()
        
        return {
            'status': 'SUCCESS',
            'embedding_array': embedding_array,
            'embedding_bytes': embedding_bytes
        }
    
    @staticmethod
    def _mock_compare_faces(source_embedding, target_embedding):
        """Mock implementation of compare_faces"""
        # Convert bytes to numpy arrays if needed
        if isinstance(source_embedding, bytes):
            source_embedding = np.frombuffer(source_embedding, dtype=np.float32)
        if isinstance(target_embedding, bytes):
            target_embedding = np.frombuffer(target_embedding, dtype=np.float32)
        
        # Compute cosine similarity
        dot_product = np.dot(source_embedding, target_embedding)
        norm_source = np.linalg.norm(source_embedding)
        norm_target = np.linalg.norm(target_embedding)
        
        similarity = dot_product / (norm_source * norm_target)
        
        return {
            'similarity': float(similarity),
            'status': 'SUCCESS'
        }
    
    @staticmethod
    def _mock_verify_identity(image_data, stored_embedding, threshold=0.6):
        """Mock implementation of verify_identity"""
        # Generate a random similarity score between 0.4 and 0.9
        similarity = 0.4 + (0.5 * np.random.rand())
        
        # Determine if verification is successful
        is_verified = similarity >= threshold
        
        return {
            'verified': is_verified,
            'status': 'SUCCESS' if is_verified else 'FAILURE',
            'confidence': similarity
        }