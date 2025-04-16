#!/usr/bin/env python3
import os
import sys
import traceback

# Set up basic error logging to file
log_file = "face_auth_error.log"

def log_error(message):
    try:
        with open(log_file, "a") as f:
            f.write(f"{message}\n")
    except:
        pass  # Silently fail if we can't write to the log file

try:
    log_error(f"Starting minimal face client at {__import__('datetime').datetime.now()}")
    log_error(f"Python version: {sys.version}")
    
    # Import core libraries
    import cv2
    import tkinter as tk
    from tkinter import ttk, messagebox
    from PIL import Image, ImageTk
    import numpy as np
    
    try:
        from pyzbar.pyzbar import decode as decode_qr
    except ImportError:
        log_error("ERROR: pyzbar not found - install with 'pip install pyzbar'")
        # Continue without it for now
    
    # Basic app class
    class MinimalFaceAuthApp:
        def __init__(self, root):
            self.root = root
            self.root.title("Minimal Face Auth Client")
            self.root.geometry("800x600")
            
            # Setup UI
            self.setup_ui()
            
            # Camera variables
            self.cap = None
            self.is_capturing = False
            
        def setup_ui(self):
            # Main frame
            main_frame = ttk.Frame(self.root, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Camera view
            self.canvas = tk.Canvas(main_frame, bg="black", width=640, height=480)
            self.canvas.pack(pady=10)
            
            # Control buttons
            btn_frame = ttk.Frame(main_frame)
            btn_frame.pack(pady=10)
            
            # Start camera button
            self.start_btn = ttk.Button(btn_frame, text="Start Camera", command=self.start_camera)
            self.start_btn.pack(side=tk.LEFT, padx=5)
            
            # Stop camera button
            self.stop_btn = ttk.Button(btn_frame, text="Stop Camera", command=self.stop_camera, state=tk.DISABLED)
            self.stop_btn.pack(side=tk.LEFT, padx=5)
            
            # Status label
            self.status_label = ttk.Label(main_frame, text="Ready")
            self.status_label.pack(pady=5)
            
        def start_camera(self):
            try:
                # Get camera device - use 0 as default
                device_id = 0
                self.cap = cv2.VideoCapture(device_id)
                
                # Set resolution
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                
                if not self.cap.isOpened():
                    log_error(f"Could not open camera {device_id}")
                    messagebox.showerror("Camera Error", f"Could not open camera {device_id}")
                    return
                
                self.is_capturing = True
                self.update_camera()
                
                # Update buttons
                self.start_btn.config(state=tk.DISABLED)
                self.stop_btn.config(state=tk.NORMAL)
                self.status_label.config(text="Camera started")
                
            except Exception as e:
                error_msg = str(e)
                log_error(f"Camera start error: {error_msg}")
                messagebox.showerror("Camera Error", f"Error starting camera: {error_msg}")
                self.stop_camera()
        
        def update_camera(self):
            if self.is_capturing and self.cap and self.cap.isOpened():
                try:
                    ret, frame = self.cap.read()
                    
                    if ret:
                        # Store the current frame
                        self.current_frame = frame.copy()
                        
                        # Process for face detection (simple version)
                        try:
                            # Convert to grayscale for face detection
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            
                            # Use face cascade classifier
                            face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                            if os.path.exists(face_cascade_path):
                                face_cascade = cv2.CascadeClassifier(face_cascade_path)
                                faces = face_cascade.detectMultiScale(gray, 1.1, 5)
                                
                                # Draw rectangles around faces
                                for (x, y, w, h) in faces:
                                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                                
                                # Add text showing face count
                                cv2.putText(frame, f"Faces: {len(faces)}", (10, 30), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        except Exception as e:
                            log_error(f"Face detection error: {str(e)}")
                            cv2.putText(frame, f"Face detection error", (10, 30), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                                                    
                        # Convert to RGB for tkinter
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        
                        # Convert to PhotoImage format
                        self.current_image = Image.fromarray(frame_rgb)
                        photo = ImageTk.PhotoImage(image=self.current_image)
                        
                        # Update canvas
                        self.canvas.create_image(0, 0, image=photo, anchor=tk.NW)
                        self.canvas.photo = photo
                    else:
                        log_error("Could not read frame from camera")
                        self.status_label.config(text="Camera error: Could not read frame")
                        
                    # Schedule the next update if still capturing
                    if self.is_capturing:
                        self.root.after(10, self.update_camera)
                except Exception as e:
                    log_error(f"Camera update error: {str(e)}")
                    self.status_label.config(text=f"Camera error: {str(e)}")
            
        def stop_camera(self):
            self.is_capturing = False
            if hasattr(self, 'cap') and self.cap and self.cap.isOpened():
                self.cap.release()
            
            # Update buttons
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            
            # Clear the canvas
            self.canvas.delete("all")
            
            self.status_label.config(text="Camera stopped")
            
        def on_closing(self):
            self.stop_camera()
            self.root.destroy()
            
    # Main entry point
    if __name__ == "__main__":
        try:
            root = tk.Tk()
            app = MinimalFaceAuthApp(root)
            root.protocol("WM_DELETE_WINDOW", app.on_closing)
            root.mainloop()
        except Exception as e:
            error_message = f"Critical error: {str(e)}"
            log_error(error_message)
            log_error(traceback.format_exc())
            
            # Try to show error graphically if possible
            try:
                import tkinter.messagebox as mb
                mb.showerror("Application Error", error_message)
            except:
                pass
            
            # Print to console as well
            print(error_message)
            traceback.print_exc()

except Exception as e:
    log_error(f"Application initialization error: {str(e)}")
    log_error(traceback.format_exc())
    print(f"ERROR: {str(e)}")
    traceback.print_exc()