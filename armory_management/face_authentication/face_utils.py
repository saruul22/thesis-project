# face_authentication/face_utils.py
import cv2
import numpy as np
import insightface  # You'll need to install this for ArcFace
from insightface.app import FaceAnalysis
import logging

logger = logging.getLogger(__name__)

class FaceRecognition:
    def __init__(self):
        try:
            # Initialize ArcFace model
            self.face_app = FaceAnalysis(name='buffalo_l')
            self.face_app.prepare(ctx_id=0, det_size=(640, 640))
        except Exception as e:
            logger.error(f"Error initializing ArcFace: {e}")
            # Fallback to a basic face detector if ArcFace fails
            self.face_app = None
            self.face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    def detect_and_encode_face(self, image):
        """Detect faces in an image and return the face encoding using ArcFace."""
        try:
            if self.face_app is not None:
                # Using ArcFace
                faces = self.face_app.get(image)
                if not faces:
                    return None
                
                # Get the largest face (assuming the person is closest to the camera)
                largest_face = max(faces, key=lambda x: x.bbox[2] * x.bbox[3])
                
                # Return the face embedding (encoding)
                return largest_face.embedding
            else:
                # Fallback to basic face detection
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                faces = self.face_detector.detectMultiScale(gray, 1.1, 4)
                
                if len(faces) == 0:
                    return None
                    
                # Get the largest face
                largest_face = sorted(faces, key=lambda x: x[2] * x[3], reverse=True)[0]
                x, y, w, h = largest_face
                
                # Extract face region and create a simple encoding (not as effective as ArcFace)
                face_img = image[y:y+h, x:x+w]
                resized = cv2.resize(face_img, (128, 128))
                flattened = resized.flatten() / 255.0
                
                return flattened
        except Exception as e:
            logger.error(f"Error in face detection: {e}")
            return None
    
    def compare_faces(self, known_encoding, face_encoding, threshold=0.6):
        """Compare two face encodings and return the similarity score."""
        if known_encoding is None or face_encoding is None:
            return 0.0
            
        try:
            if self.face_app is not None:
                # Using ArcFace similarity metric
                similarity = np.dot(known_encoding, face_encoding) / (
                    np.linalg.norm(known_encoding) * np.linalg.norm(face_encoding)
                )
                return float(similarity)
            else:
                # Fallback to simple Euclidean distance for basic encoding
                distance = np.linalg.norm(np.array(known_encoding) - np.array(face_encoding))
                similarity = 1.0 - min(distance / 100.0, 1.0)  # Normalize to 0-1
                return float(similarity)
        except Exception as e:
            logger.error(f"Error comparing faces: {e}")
            return 0.0