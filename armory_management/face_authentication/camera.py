# face_authentication/camera.py
import cv2
import threading
import logging

logger = logging.getLogger(__name__)

class Camera:
    def __init__(self):
        self.camera = None
        self.frame = None
        self.stopped = False
        
    def start(self):
        if self.camera is None:
            self.camera = cv2.VideoCapture(0)
            
        if not self.camera.isOpened():
            logger.error("Could not open camera")
            raise ValueError("Could not open camera")
            
        # Start thread to read frames
        self.stopped = False
        threading.Thread(target=self._update, daemon=True).start()
        return self
    
    def _update(self):
        while not self.stopped:
            ret, frame = self.camera.read()
            if ret:
                self.frame = frame
            else:
                logger.warning("Failed to read frame from camera")
                break
    
    def read(self):
        return self.frame
    
    def stop(self):
        self.stopped = True
        if self.camera is not None:
            self.camera.release()
            logger.info("Camera released")