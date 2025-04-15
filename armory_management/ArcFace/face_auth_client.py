import os
import sys
import cv2
import json
import base64
import requests
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import configparser
from datetime import datetime
import threading
import queue
from pyzbar.pyzbar import decode as decode_qr

# Import local ArcFace processor for offline mode
try:
    from local_arcface import LocalArcFaceProcessor
except ImportError:
    LocalArcFaceProcessor = None

class FaceAuthClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Weapon System Authentication")
        self.root.geometry("1000x700")
        self.root.resizable(True, True)
        
        # Load configuration
        self.config = self.load_config()
        
        # Set API endpoint
        self.api_base_url = self.config.get('api', 'base_url')
        self.api_token = self.config.get('api', 'token', fallback=None)
        
        # Initialize webcam
        self.cap = None
        self.is_capturing = False
        
        # Check offline mode
        self.offline_mode = self.config.getboolean('app', 'offline_mode', fallback=False)
        self.local_db_path = self.config.get('app', 'local_db_path', fallback='face_db')
        self.similarity_threshold = self.config.getfloat('app', 'similarity_threshold', fallback=0.6)
        
        # Initialize local face processor if in offline mode
        self.local_processor = None
        if self.offline_mode and LocalArcFaceProcessor is not None:
            try:
                self.local_processor = LocalArcFaceProcessor(models_dir=self.local_db_path)
                print("Local ArcFace processor initialized")
            except Exception as e:
                print(f"Failed to initialize local processor: {str(e)}")
                messagebox.showwarning("Offline Mode", 
                    f"Failed to initialize local face recognition. Switching to online mode.\nError: {str(e)}")
                self.offline_mode = False
        elif self.offline_mode:
            messagebox.showwarning("Offline Mode", 
                "Local ArcFace processor not available. Please install dlib and its dependencies.")
            self.offline_mode = False
        
        # Create UI
        self.create_ui()
        
        # Status variables
        self.personnel_id = None
        self.verified = False
        self.qr_scanned = False
        self.qr_data = None
        
        # Processing queue for background tasks
        self.task_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self.process_tasks, daemon=True)
        self.worker_thread.start()
        
    def load_config(self):
        """Load configuration from config.ini file"""
        config = configparser.ConfigParser()
        
        # Default configuration
        config['api'] = {
            'base_url': 'http://localhost:8000/api/face',
            'token': ''
        }
        config['camera'] = {
            'device_id': '0',
            'width': '640',
            'height': '480'
        }
        config['app'] = {
            'offline_mode': 'false',
            'local_db_path': 'face_db',
            'similarity_threshold': '0.6'
        }
        
        # Try to load from file
        if os.path.exists('config.ini'):
            config.read('config.ini')
        else:
            # Save default config
            with open('config.ini', 'w') as f:
                config.write(f)
                
        return config
        
    def create_ui(self):
        """Create the UI elements"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="Weapon System Authentication", font=("Arial", 18, "bold"))
        title_label.pack(pady=10)
        
        # Create tabs
        tab_control = ttk.Notebook(main_frame)
        
        authentication_tab = ttk.Frame(tab_control)
        register_tab = ttk.Frame(tab_control)
        settings_tab = ttk.Frame(tab_control)
        
        tab_control.add(authentication_tab, text="Authentication")
        tab_control.add(register_tab, text="Register Face")
        tab_control.add(settings_tab, text="Settings")
        
        tab_control.pack(expand=True, fill=tk.BOTH)
        
        # ---- Authentication Tab ----
        self.setup_authentication_tab(authentication_tab)
        
        # ---- Register Face Tab ----
        self.setup_register_tab(register_tab)
        
        # ---- Settings Tab ----
        self.setup_settings_tab(settings_tab)
        
        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.pack(side=tk.LEFT)
        
        self.connection_label = ttk.Label(status_frame, text="Not connected")
        self.connection_label.pack(side=tk.RIGHT)
        
        # Check connection
        self.check_connection()
    
    def setup_authentication_tab(self, parent):
        """Setup the unified authentication tab"""
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel (camera feed)
        left_panel = ttk.Frame(frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Camera feed
        self.auth_canvas = tk.Canvas(left_panel, bg="black", width=640, height=480)
        self.auth_canvas.pack(pady=10)
        
        # Camera controls
        camera_controls = ttk.Frame(left_panel)
        camera_controls.pack(pady=10)
        
        self.auth_start_btn = ttk.Button(camera_controls, text="Start Authentication", 
                                      command=lambda: self.start_camera(canvas=self.auth_canvas, mode="authentication"))
        self.auth_start_btn.pack(side=tk.LEFT, padx=5)
        
        self.auth_stop_btn = ttk.Button(camera_controls, text="Stop", 
                                     command=self.stop_camera, state=tk.DISABLED)
        self.auth_stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.auth_capture_btn = ttk.Button(camera_controls, text="Capture Face", 
                                        command=self.capture_face_for_auth, state=tk.DISABLED)
        self.auth_capture_btn.pack(side=tk.LEFT, padx=5)
        
        # Right panel (authentication info)
        right_panel = ttk.Frame(frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10)
        
        # Transaction type selection
        transaction_frame = ttk.Frame(right_panel)
        transaction_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(transaction_frame, text="Transaction:").pack(side=tk.LEFT)
        self.transaction_type = tk.StringVar(value="check_in")
        ttk.Radiobutton(transaction_frame, text="Check In", variable=self.transaction_type, 
                      value="check_in").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(transaction_frame, text="Check Out", variable=self.transaction_type, 
                      value="check_out").pack(side=tk.LEFT, padx=10)
        
        # Authentication status
        status_frame = ttk.LabelFrame(right_panel, text="Authentication Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # QR status
        self.qr_status_label = ttk.Label(status_frame, text="Step 1: Scan Weapon QR Code", font=("Arial", 12))
        self.qr_status_label.pack(pady=5)
        
        self.weapon_info_label = ttk.Label(status_frame, text="No weapon scanned")
        self.weapon_info_label.pack(pady=5)
        
        # Personnel info from QR code
        self.personnel_info_label = ttk.Label(status_frame, text="")
        self.personnel_info_label.pack(pady=5)
        
        # Face verification status
        self.face_status_label = ttk.Label(status_frame, text="Step 2: Face Verification (waiting)", font=("Arial", 12))
        self.face_status_label.pack(pady=5)
        
        self.face_result_label = ttk.Label(status_frame, text="")
        self.face_result_label.pack(pady=5)
        
        # Overall status
        self.auth_result_label = ttk.Label(status_frame, text="", font=("Arial", 14, "bold"))
        self.auth_result_label.pack(pady=10)
        
        # Reset button
        self.auth_reset_btn = ttk.Button(right_panel, text="Reset", command=self.reset_authentication, state=tk.DISABLED)
        self.auth_reset_btn.pack(pady=10, fill=tk.X)
    
    def setup_register_tab(self, parent):
        """Setup the registration tab"""
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel (camera feed)
        left_panel = ttk.Frame(frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Camera feed
        self.register_canvas = tk.Canvas(left_panel, bg="black", width=640, height=480)
        self.register_canvas.pack(pady=10)
        
        # Camera controls
        camera_controls = ttk.Frame(left_panel)
        camera_controls.pack(pady=10)
        
        self.reg_start_btn = ttk.Button(camera_controls, text="Start Camera", 
                                      command=lambda: self.start_camera(canvas=self.register_canvas, mode="register"))
        self.reg_start_btn.pack(side=tk.LEFT, padx=5)
        
        self.reg_stop_btn = ttk.Button(camera_controls, text="Stop Camera", 
                                     command=self.stop_camera, state=tk.DISABLED)
        self.reg_stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.reg_capture_btn = ttk.Button(camera_controls, text="Capture", 
                                        command=self.capture_registration_image, state=tk.DISABLED)
        self.reg_capture_btn.pack(side=tk.LEFT, padx=5)
        
        # Right panel (registration info)
        right_panel = ttk.Frame(frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10)
        
        # Personnel ID input
        reg_id_frame = ttk.Frame(right_panel)
        reg_id_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(reg_id_frame, text="Personnel ID:").pack(side=tk.LEFT)
        
        self.reg_id_var = tk.StringVar()
        reg_id_entry = ttk.Entry(reg_id_frame, textvariable=self.reg_id_var)
        reg_id_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Registration status
        status_frame = ttk.LabelFrame(right_panel, text="Registration Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.reg_status_label = ttk.Label(status_frame, text="Not registered", font=("Arial", 14))
        self.reg_status_label.pack(pady=10)
        
        self.reg_info_label = ttk.Label(status_frame, text="")
        self.reg_info_label.pack(pady=5)
        
        # Register button
        self.register_btn = ttk.Button(right_panel, text="Register Face", command=self.register_face, state=tk.DISABLED)
        self.register_btn.pack(pady=10, fill=tk.X)
    
    def setup_settings_tab(self, parent):
        """Setup the settings tab"""
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # API Settings
        api_frame = ttk.LabelFrame(frame, text="API Settings", padding="10")
        api_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(api_frame, text="API Base URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.api_url_var = tk.StringVar(value=self.api_base_url)
        ttk.Entry(api_frame, textvariable=self.api_url_var, width=40).grid(row=0, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(api_frame, text="API Token:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.api_token_var = tk.StringVar(value=self.api_token if self.api_token else "")
        ttk.Entry(api_frame, textvariable=self.api_token_var, width=40, show="*").grid(row=1, column=1, sticky=tk.W, pady=5)
        
        # Camera Settings
        cam_frame = ttk.LabelFrame(frame, text="Camera Settings", padding="10")
        cam_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(cam_frame, text="Camera Device ID:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.cam_id_var = tk.StringVar(value=self.config.get('camera', 'device_id'))
        ttk.Entry(cam_frame, textvariable=self.cam_id_var, width=10).grid(row=0, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(cam_frame, text="Resolution:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        res_frame = ttk.Frame(cam_frame)
        res_frame.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        self.cam_width_var = tk.StringVar(value=self.config.get('camera', 'width'))
        self.cam_height_var = tk.StringVar(value=self.config.get('camera', 'height'))
        
        ttk.Entry(res_frame, textvariable=self.cam_width_var, width=6).pack(side=tk.LEFT)
        ttk.Label(res_frame, text="x").pack(side=tk.LEFT, padx=2)
        ttk.Entry(res_frame, textvariable=self.cam_height_var, width=6).pack(side=tk.LEFT)
        
        # Offline Mode Settings
        offline_frame = ttk.LabelFrame(frame, text="Offline Mode Settings", padding="10")
        offline_frame.pack(fill=tk.X, pady=10)
        
        # Offline mode checkbox
        self.offline_mode_var = tk.BooleanVar(value=self.offline_mode)
        ttk.Checkbutton(offline_frame, text="Enable Offline Mode", 
                       variable=self.offline_mode_var).grid(row=0, column=0, sticky=tk.W, pady=5)
        
        # Local database path
        ttk.Label(offline_frame, text="Local Database Path:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.local_db_path_var = tk.StringVar(value=self.local_db_path)
        ttk.Entry(offline_frame, textvariable=self.local_db_path_var, width=40).grid(row=1, column=1, sticky=tk.W, pady=5)
        
        # Similarity threshold
        ttk.Label(offline_frame, text="Similarity Threshold:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.threshold_var = tk.StringVar(value=str(self.similarity_threshold))
        ttk.Entry(offline_frame, textvariable=self.threshold_var, width=10).grid(row=2, column=1, sticky=tk.W, pady=5)
        
        # Local processor status
        processor_status = "Available" if LocalArcFaceProcessor is not None else "Not Available"
        ttk.Label(offline_frame, text=f"Local Processor: {processor_status}").grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Button to sync with server
        if LocalArcFaceProcessor is not None:
            ttk.Button(offline_frame, text="Sync with Server", 
                      command=self.sync_with_server).grid(row=4, column=0, columnspan=2, pady=5)
        
        # Save button
        ttk.Button(frame, text="Save Settings", command=self.save_settings).pack(pady=10)
        
        # Test connection button
        ttk.Button(frame, text="Test Connection", command=self.check_connection).pack(pady=5)

    def save_settings(self):
        """Save settings to config file"""
        self.config.set('api', 'base_url', self.api_url_var.get())
        self.config.set('api', 'token', self.api_token_var.get())
        self.config.set('camera', 'device_id', self.cam_id_var.get())
        self.config.set('camera', 'width', self.cam_width_var.get())
        self.config.set('camera', 'height', self.cam_height_var.get())
        
        # Save offline mode settings
        new_offline_mode = self.offline_mode_var.get()
        self.config.set('app', 'offline_mode', str(new_offline_mode))
        self.config.set('app', 'local_db_path', self.local_db_path_var.get())
        
        try:
            threshold = float(self.threshold_var.get())
            if 0 <= threshold <= 1:
                self.config.set('app', 'similarity_threshold', str(threshold))
            else:
                messagebox.showwarning("Invalid Value", "Similarity threshold must be between 0 and 1")
                self.threshold_var.set(str(self.similarity_threshold))
        except ValueError:
            messagebox.showwarning("Invalid Value", "Similarity threshold must be a number")
            self.threshold_var.set(str(self.similarity_threshold))
        
        with open('config.ini', 'w') as f:
            self.config.write(f)
        
        # Update instance variables
        self.api_base_url = self.api_url_var.get()
        self.api_token = self.api_token_var.get()
        self.local_db_path = self.local_db_path_var.get()
        self.similarity_threshold = float(self.threshold_var.get())
        
        # Handle offline mode change
        if new_offline_mode != self.offline_mode:
            self.offline_mode = new_offline_mode
            if new_offline_mode and LocalArcFaceProcessor is not None:
                try:
                    self.local_processor = LocalArcFaceProcessor(models_dir=self.local_db_path)
                    messagebox.showinfo("Offline Mode", "Local face processor initialized")
                except Exception as e:
                    messagebox.showerror("Offline Mode Error", f"Failed to initialize local processor: {str(e)}")
                    self.offline_mode = False
                    self.offline_mode_var.set(False)
                    self.config.set('app', 'offline_mode', 'false')
                    with open('config.ini', 'w') as f:
                        self.config.write(f)
            elif new_offline_mode:
                messagebox.showwarning("Offline Mode", 
                    "Local ArcFace processor not available. Please install dlib and its dependencies.")
                self.offline_mode = False
                self.offline_mode_var.set(False)
                self.config.set('app', 'offline_mode', 'false')
                with open('config.ini', 'w') as f:
                    self.config.write(f)
        
        messagebox.showinfo("Settings", "Settings saved successfully")
        
        # Check connection with new settings if not in offline mode
        if not self.offline_mode:
            self.check_connection()
    
    def sync_with_server(self):
        """Synchronize local database with server"""
        if not self.local_processor:
            messagebox.showerror("Sync Error", "Local processor not available")
            return
        
        # Check if we have a token for authentication
        if not self.api_token:
            messagebox.showwarning("Sync Warning", "API token not set. Authentication may fail.")
        
        # Confirm sync
        if not messagebox.askyesno("Confirm Sync", 
                                  "This will download face data from the server. Continue?"):
            return
        
        # Disable UI during sync
        self.status_label.config(text="Syncing with server...")
        
        # Use a background thread to avoid freezing the UI
        def sync_task():
            try:
                # Set headers
                headers = {'Content-Type': 'application/json'}
                if self.api_token:
                    headers['Authorization'] = f'Token {self.api_token}'
                
                # Get list of personnel with face records
                url = f"{self.api_base_url.rstrip('/')}/list_faces/"
                response = requests.get(url, headers=headers, timeout=30)
                
                if response.status_code != 200:
                    return {
                        'success': False,
                        'error': f"Failed to retrieve face list: {response.text}",
                        'status': "Sync failed"
                    }
                
                personnel_list = response.json()
                
                # Track success and failures
                success_count = 0
                fail_count = 0
                
                # Download each face record
                for person in personnel_list.get('records', []):
                    personnel_id = person.get('personnel_id')
                    
                    if not personnel_id:
                        fail_count += 1
                        continue
                    
                    # Get face data
                    face_url = f"{self.api_base_url.rstrip('/')}/get_face_data/{personnel_id}/"
                    face_response = requests.get(face_url, headers=headers, timeout=30)
                    
                    if face_response.status_code != 200:
                        fail_count += 1
                        continue
                    
                    face_data = face_response.json()
                    
                    # Extract embedding
                    embedding_b64 = face_data.get('embedding')
                    if not embedding_b64:
                        fail_count += 1
                        continue
                    
                    # Decode embedding
                    embedding_bytes = base64.b64decode(embedding_b64)
                    embedding_array = np.frombuffer(embedding_bytes, dtype=np.float32)
                    
                    # Store in local database
                    self.local_processor.embeddings_db[personnel_id] = embedding_array
                    success_count += 1
                
                # Save database
                self.local_processor.save_embeddings_db()
                
                return {
                    'success': True,
                    'message': f"Sync complete. {success_count} records synchronized, {fail_count} failed.",
                    'status': "Sync complete"
                }
                
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'status': "Sync failed"
                }
        
        # Queue the task
        self.task_queue.put((sync_task, self.handle_sync_result))
    
    def handle_sync_result(self, result):
        """Handle the sync result"""
        if result['success']:
            messagebox.showinfo("Sync Complete", result['message'])
        else:
            messagebox.showerror("Sync Failed", result['error'])
        
        self.status_label.config(text=result['status'])
    
    def check_connection(self):
        """Check connection to the API"""
        if self.offline_mode:
            self.connection_label.config(text="Offline Mode", foreground="blue")
            return True
            
        try:
            headers = {}
            if self.api_token:
                headers['Authorization'] = f'Token {self.api_token}'
            
            # Send a simple request to check if the API is accessible
            response = requests.get(f"{self.api_base_url.rstrip('/')}/verify/", 
                                   timeout=3,
                                   headers=headers)
            
            if response.status_code in [200, 401, 403, 404]:  # Any of these means server is up
                self.connection_label.config(text="Connected", foreground="green")
                return True
            else:
                self.connection_label.config(text="Connection Error", foreground="red")
                return False
                
        except requests.exceptions.RequestException:
            self.connection_label.config(text="Connection Error", foreground="red")
            return False
    
    def start_camera(self, canvas=None, mode=None):
        """Start the webcam feed"""
        # Store the current mode
        self.current_mode = mode
        self.active_canvas = canvas
        
        # Reset states for authentication process if needed
        if mode == "authentication":
            self.qr_scanned = False
            self.qr_data = None
            self.personnel_id = None
            self.qr_status_label.config(text="Step 1: Scan Weapon QR Code", foreground="black")
            self.face_status_label.config(text="Step 2: Face Verification (waiting)", foreground="gray")
            self.weapon_info_label.config(text="No weapon scanned")
            self.personnel_info_label.config(text="")
            self.face_result_label.config(text="")
            self.auth_result_label.config(text="")
            self.auth_capture_btn.config(state=tk.DISABLED)
            self.auth_reset_btn.config(state=tk.DISABLED)
            
            # Update buttons
            self.auth_start_btn.config(state=tk.DISABLED)
            self.auth_stop_btn.config(state=tk.NORMAL)
            self.reg_start_btn.config(state=tk.DISABLED)
            
        elif mode == "register":
            # Update buttons for register mode
            self.reg_start_btn.config(state=tk.DISABLED)
            self.reg_stop_btn.config(state=tk.NORMAL)
            self.reg_capture_btn.config(state=tk.NORMAL)
            self.auth_start_btn.config(state=tk.DISABLED)
        
        try:
            device_id = int(self.config.get('camera', 'device_id'))
            self.cap = cv2.VideoCapture(device_id)
            
            # Set resolution
            width = int(self.config.get('camera', 'width'))
            height = int(self.config.get('camera', 'height'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            
            if not self.cap.isOpened():
                messagebox.showerror("Camera Error", f"Could not open camera device {device_id}")
                self.stop_camera()
                return
            
            self.is_capturing = True
            self.update_camera()
            self.status_label.config(text="Camera started")
            
        except Exception as e:
            messagebox.showerror("Camera Error", f"Error starting camera: {str(e)}")
            self.stop_camera()
    
    def update_camera(self):
        """Update the camera feed on the canvas"""
        if self.is_capturing and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # Store the original frame
                self.current_frame = frame.copy()
                
                # Handle different modes
                if hasattr(self, 'current_mode') and self.current_mode == "authentication":
                    if not self.qr_scanned:
                        # In QR scanning mode
                        qr_codes = decode_qr(frame)
                        if qr_codes:
                            for qr in qr_codes:
                                # Draw rectangle around QR code
                                points = qr.polygon
                                if len(points) > 4:
                                    hull = cv2.convexHull(
                                        np.array([(p.x, p.y) for p in points], dtype=np.int32))
                                    cv2.polylines(frame, [hull], True, (0, 255, 0), 2)
                                else:
                                    cv2.polylines(
                                        frame, 
                                        [np.array([(p.x, p.y) for p in points], dtype=np.int32)], 
                                        True, 
                                        (0, 255, 0), 
                                        2
                                    )
                                
                                # Process QR data
                                self.qr_data = qr.data.decode('utf-8')
                                self.qr_scanned = True
                                self.qr_status_label.config(text="Step 1: QR Code Scanned ✓", foreground="green")
                                
                                # Get weapon and personnel info from server
                                self.get_weapon_and_personnel_info(self.qr_data)
                    else:
                        # In face verification mode (after QR is scanned)
                        # Here you could add face detection visualization
                        pass
                
                # Convert to RGB for tkinter
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Convert to PhotoImage format
                self.current_image = Image.fromarray(frame_rgb)
                photo = ImageTk.PhotoImage(image=self.current_image)
                
                # Update canvas
                self.active_canvas.create_image(0, 0, image=photo, anchor=tk.NW)
                self.active_canvas.photo = photo
            
            # Schedule the next update
            self.root.after(10, self.update_camera)
    
    def stop_camera(self):
        """Stop the webcam feed"""
        self.is_capturing = False
        if hasattr(self, 'cap') and self.cap and self.cap.isOpened():
            self.cap.release()
        
        if hasattr(self, 'current_mode'):
            if self.current_mode == "authentication":
                self.auth_start_btn.config(state=tk.NORMAL)
                self.auth_stop_btn.config(state=tk.DISABLED)
                self.auth_capture_btn.config(state=tk.DISABLED)
                self.reg_start_btn.config(state=tk.NORMAL)
            elif self.current_mode == "register":
                self.reg_start_btn.config(state=tk.NORMAL)
                self.reg_stop_btn.config(state=tk.DISABLED)
                self.reg_capture_btn.config(state=tk.DISABLED)
                self.register_btn.config(state=tk.DISABLED)
                self.auth_start_btn.config(state=tk.NORMAL)
        
        self.status_label.config(text="Camera stopped")
    
    def get_weapon_and_personnel_info(self, qr_data):
        """Get weapon information and associated personnel from the server based on QR code"""
        try:
            # Prepare headers
            headers = {'Content-Type': 'application/json'}
            if self.api_token:
                headers['Authorization'] = f'Token {self.api_token}'
            
            # Send request to your server
            url = f"{self.api_base_url.rstrip('/')}/weapon/info/"
            response = requests.post(
                url, 
                json={"qr_code": qr_data, "transaction_type": self.transaction_type.get()}, 
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Display weapon info
                weapon_info = result.get('weapon_info', {})
                self.weapon_info_label.config(
                    text=f"Weapon: {weapon_info.get('model', 'Unknown')} - {weapon_info.get('serial_number', 'Unknown')}"
                )
                
                # Store and display personnel info
                self.personnel_id = result.get('personnel_id')
                personnel_info = result.get('personnel_info', {})
                
                if self.personnel_id:
                    self.personnel_info_label.config(
                        text=f"Personnel: {personnel_info.get('rank', '')} {personnel_info.get('name', 'Unknown')} ({self.personnel_id})"
                    )
                    self.face_status_label.config(text="Step 2: Face Verification (active)", foreground="black")
                    # Enable capture button now that we have a personnel ID
                    self.auth_capture_btn.config(state=tk.NORMAL)
                else:
                    self.personnel_info_label.config(text="No personnel assigned to this weapon")
                    # Handle based on transaction type
                    if self.transaction_type.get() == "check_in":
                        self.face_status_label.config(text="Step 2: Cannot check in - no assigned personnel", foreground="red")
                    else:  # check_out
                        self.face_status_label.config(text="Step 2: Ready for assignment", foreground="blue")
                        # Ask for personnel ID for checkout
                        personnel_id = simpledialog.askstring("Input", "Enter Personnel ID for weapon assignment:")
                        if personnel_id:
                            self.personnel_id = personnel_id
                            self.personnel_info_label.config(text=f"Personnel ID for assignment: {personnel_id}")
                            self.auth_capture_btn.config(state=tk.NORMAL)
                        else:
                            self.reset_authentication()
                
            else:
                error_message = f"Could not retrieve weapon information: {response.text}"
                self.weapon_info_label.config(text=f"Error: {error_message}")
                messagebox.showerror("Error", error_message)
                self.reset_authentication()
                
        except Exception as e:
            error_message = f"Error getting weapon info: {str(e)}"
            self.weapon_info_label.config(text=f"Error: {error_message}")
            messagebox.showerror("Error", error_message)
            self.reset_authentication()
    
    def capture_face_for_auth(self):
        """Capture face image for authentication"""
        if not self.qr_scanned:
            messagebox.showwarning("Workflow Error", "Please scan a QR code first")
            return
        
        if not hasattr(self, 'current_frame') or self.current_frame is None:
            messagebox.showerror("Error", "No frame to capture")
            return
        
        if not hasattr(self, 'personnel_id') or not self.personnel_id:
            if self.transaction_type.get() == "check_in":
                messagebox.showerror("Error", "No personnel assigned to this weapon")
                return
            else:
                # For check-out, we need to ask for personnel ID
                personnel_id = simpledialog.askstring("Input", "Enter Personnel ID for weapon assignment:")
                if not personnel_id:
                    return
                self.personnel_id = personnel_id
                self.personnel_info_label.config(text=f"Personnel ID for assignment: {personnel_id}")
        
        # Store captured frame
        self.captured_frame = self.current_frame.copy()
        
        # Process face verification with the stored personnel ID
        self.auth_capture_btn.config(state=tk.DISABLED)
        self.verify_face_for_transaction(self.personnel_id, self.captured_frame, self.qr_data)
    
    def verify_face_for_transaction(self, personnel_id, frame, qr_data):
        """Verify face and complete transaction"""
        try:
            # Convert frame to JPEG format
            _, buffer = cv2.imencode('.jpg', frame)
            
            # Convert to base64
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Prepare data for API
            data = {
                'personnel_id': personnel_id,
                'face_image': img_base64,
                'qr_code': qr_data,
                'transaction_type': self.transaction_type.get()
            }
            
            # Set headers
            headers = {'Content-Type': 'application/json'}
            if self.api_token:
                headers['Authorization'] = f'Token {self.api_token}'
            
            # Send request
            url = f"{self.api_base_url.rstrip('/')}/weapon/transaction/"
            
            # Update status
            self.status_label.config(text="Processing transaction...")
            self.face_status_label.config(text="Step 2: Verifying face...", foreground="blue")
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('verified', False):
                    self.face_status_label.config(text="Step 2: Face Verified ✓", foreground="green")
                    self.face_result_label.config(text=f"Confidence: {result.get('confidence', 0) * 100:.2f}%")
                    
                    # Display transaction result
                    if result.get('transaction_success', False):
                        transaction_type = "CHECK-IN" if self.transaction_type.get() == "check_in" else "CHECK-OUT"
                        self.auth_result_label.config(text=f"{transaction_type} SUCCESSFUL", foreground="green")
                    else:
                        self.auth_result_label.config(
                            text=f"TRANSACTION FAILED: {result.get('message', '')}", 
                            foreground="red"
                        )
                else:
                    self.face_status_label.config(text="Step 2: Face Verification Failed ✗", foreground="red")
                    self.face_result_label.config(text=f"Confidence: {result.get('confidence', 0) * 100:.2f}%")
                    self.auth_result_label.config(text="TRANSACTION FAILED: Face verification failed", foreground="red")
            else:
                self.face_status_label.config(text="Step 2: Verification Error ✗", foreground="red")
                self.auth_result_label.config(text=f"TRANSACTION FAILED: {response.text}", foreground="red")
                
        except Exception as e:
            self.face_status_label.config(text="Step 2: Verification Error ✗", foreground="red")
            self.auth_result_label.config(text=f"TRANSACTION FAILED: {str(e)}", foreground="red")
        
        # Enable reset button
        self.auth_reset_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Transaction complete")
    
    def reset_authentication(self):
        """Reset the authentication process"""
        self.qr_scanned = False
        self.qr_data = None
        self.personnel_id = None
        
        self.qr_status_label.config(text="Step 1: Scan Weapon QR Code", foreground="black")
        self.weapon_info_label.config(text="No weapon scanned")
        self.personnel_info_label.config(text="")
        self.face_status_label.config(text="Step 2: Face Verification (waiting)", foreground="gray")
        self.face_result_label.config(text="")
        self.auth_result_label.config(text="")
        
        self.auth_capture_btn.config(state=tk.DISABLED)
        self.auth_reset_btn.config(state=tk.DISABLED)
        
        self.status_label.config(text="Authentication reset")
    
    def capture_registration_image(self):
        """Capture image for registration"""
        if not hasattr(self, 'current_frame') or self.current_frame is None:
            messagebox.showerror("Error", "No frame to capture")
            return
        
        # Store captured frame
        self.captured_frame = self.current_frame.copy()
        self.status_label.config(text="Image captured for registration")
        self.register_btn.config(state=tk.NORMAL)
    
    def register_face(self):
        """Register face with the server or locally"""
        if not hasattr(self, 'captured_frame'):
            messagebox.showerror("Error", "No image captured")
            return
        
        personnel_id = self.reg_id_var.get().strip()
        if not personnel_id:
            messagebox.showerror("Error", "Personnel ID is required")
            return
        
        # Disable button during registration
        self.register_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Registering face...")
        
        # Use a background thread to avoid freezing the UI
        def registration_task():
            if self.offline_mode and self.local_processor:
                # Use local processor for registration
                return self.register_face_locally(personnel_id, self.captured_frame)
            else:
                # Use server API for registration
                return self.register_face_online(personnel_id, self.captured_frame)
        
        # Queue the task
        self.task_queue.put((registration_task, self.handle_registration_result))
    
    def register_face_locally(self, personnel_id, frame):
        """Register face using local processor"""
        try:
            # Register using local processor
            success = self.local_processor.register_face(personnel_id, frame)
            
            if success:
                return {
                    'success': True,
                    'created': True,
                    'face_id': personnel_id,
                    'status': "Registration complete using local processor"
                }
            else:
                return {
                    'success': False,
                    'error': "Failed to detect face or extract features",
                    'status': "Local registration failed"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'status': "Local registration failed"
            }
    
    def register_face_online(self, personnel_id, frame):
        """Register face using server API"""
        try:
            # Convert frame to JPEG format
            _, buffer = cv2.imencode('.jpg', frame)
            
            # Convert to base64
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Prepare data for API
            data = {
                'personnel_id': personnel_id,
                'face_image': img_base64
            }
            
            # Set headers
            headers = {'Content-Type': 'application/json'}
            if self.api_token:
                headers['Authorization'] = f'Token {self.api_token}'
            
            # Send request
            url = f"{self.api_base_url.rstrip('/')}/register/"
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code in [200, 201]:
                # Success
                result = response.json()
                
                return {
                    'success': True,
                    'created': result.get('created', True),
                    'face_id': result.get('face_id', 'Unknown'),
                    'status': "Registration complete"
                }
                
            elif response.status_code == 404:
                return {
                    'success': False,
                    'error': "Personnel ID not found in the system",
                    'status': "Registration failed - ID not found"
                }
                
            else:
                # Error
                return {
                    'success': False,
                    'error': f"API Error: {response.text}",
                    'status': "Registration failed"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'status': "Registration failed - connection error"
            }
        
    def handle_verification_result(self, result):
        """Handle the verification result and update UI"""
        # Re-enable button if needed
        self.verify_btn.config(state=tk.NORMAL)

        if result['success']:
            api_result = result['result']

            if api_result.get('verified', False):
                self.verify_result_label.config(text="VERIFIED", foreground="green")
                self.confidence_label.config(text=f"Configence: {api_result.get('confidence', 0) * 100:.2f}")
            else:
                self.verify_result_label.config(text="NOT VERIFIED", foreground="red")
                self.confidence_label.config(text=f"Confidence: {api_result.get('confidence', 0) * 100:.2f}")
            
            # Update time
            self.verify_time_label.config(text=f"Time: {result['time']}")

        else:
            self.verify_result_label.config(text="ERROR", foreground="red")
            self.confidence_label.config(text="Confidence: 0%")
            messagebox.showerror("Verification Error", result['error'])

        self.status_label.config(text=result['status'])
    
    def handle_registration_result(self, result):
        """Handle the registration result and update UI"""
        # Re-enable button
        self.register_btn.config(state=tk.NORMAL)
        
        if result['success']:
            self.reg_status_label.config(text="REGISTERED", foreground="green")
            created = result.get('created', True)
            self.reg_info_label.config(
                text=f"Face ID: {result.get('face_id', 'N/A')}\nStatus: {'Created' if created else 'Updated'}"
            )
            
            messagebox.showinfo("Registration", "Face registered successfully")
            
        else:
            self.reg_status_label.config(text="ERROR", foreground="red")
            self.reg_info_label.config(text="")
            messagebox.showerror("Registration Error", result['error'])
        
        self.status_label.config(text=result['status'])

    def verify_face_for_transaction(self, personnel_id, frame, qr_data):
        """Verify face and complete transaction with auto-reset"""
        try:
            # Convert frame to JPEG format
            _, buffer = cv2.imencode('.jpg', frame)

            # Convert to base64
            img_base64 = base64.b64encode(buffer).decode('utf-8')

            # Prepare data for API
            data = {
                'personnel_id': personnel_id,
                'face_image': img_base64,
                'qr_code': qr_data,
                'transaction_type': self.transaction_type.get()
            }

            # Set headers
            headers = {'Content-Type': 'application/json'}
            if self.api_token:
                headers['Authorization'] = f'Token {self.api_token}'

            # Send request
            url = f"{self.api_base_url.rstrip('/')}/weapon/transaction/"

            # Update status
            self.status_label.config(text="Processing transaction...")
            self.face_status_label.config(text="Step 2: Verifying face...", foreground="blue")

            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()

                if result.get('verified', False):
                    self.face_status_label.config(text="Step 2: Face Verified ✓", foreground="green")
                    self.face_result_label.config(text=f"Confidence: {result.get('confidence', 0) * 100:.2f}%")

                    # Display transaction result
                    if result.get('transaction_success', False):
                        transaction_type = "CHECK-IN" if self.transaction_type.get() == 'check_in' else "CHECK-OUT"
                        self.auth_result_label.config(text=f"{transaction_type} SUCCESSFUL", foreground="green")

                        # Schedule auto-reset after successful transaction
                        self.root.after(3000, self.auto_reset_for_next_transaction)
                    else:
                        self.auth_result_label.config(
                            text=f"TRANSACTION FAILED: {result.get('message', '')}", 
                            foreground="red"
                        )
                        # Enable reset button for failed transactions
                        self.auth_reset_btn.config(state=tk.NORMAL)
                else:
                    self.face_status_label.config(text="Step 2: Face Verification Failed ✗", foreground="red")
                    self.face_result_label.config(text=f"Confidence: {result.get('confidence', 0) * 100:.2f}%")
                    self.auth_result_label.config(text="TRANSACTION FAILED: Face verification failed", foreground="red")
                    # Enable reset button for failed transactions
                    self.auth_reset_btn.config(state=tk.NORMAL)
            else:
                self.face_status_label.config(text="Step 2: Verification Error ✗", foreground="red")
                self.auth_result_label.config(text=f"TRANSACTION FAILED: {response.text}", foreground="red")
                # Enable reset button for failed transactions
                self.auth_reset_btn.config(state=tk.NORMAL)

        except Exception as e:
            self.face_status_label.config(text="Step 2: Verification Error ✗", foreground="red")
            self.auth_result_label.config(text=f"TRANSACTION FAILED: {str(e)}", foreground="red")
            # Enable reset button for failed transactions
            self.auth_reset_btn.config(state=tk.NORMAL)

        self.status_label.config(text="Transaction complete")

    def auto_reset_for_next_transaction(self):
        """Automatically reset after successful transaction"""
        self.reset_authentication()
        
        # Optional: Play a sound or show a temporary message
        self.status_label.config(text="Ready for next transaction")
        
        # You could also flash the screen briefly to indicate readiness
        original_bg = self.auth_canvas.cget("background")
        self.auth_canvas.config(background="green")
        self.root.after(200, lambda: self.auth_canvas.config(background=original_bg))
    
    def process_tasks(self):
        """Process tasks from the queue in background"""
        while True:
            try:
                # Get a task from the queue
                task_func, callback = self.task_queue.get(block=True)
                
                # Execute the task
                result = task_func()
                
                # Schedule the callback in the main thread
                self.root.after(0, lambda r=result: callback(r))
                
                # Mark task as done
                self.task_queue.task_done()
                
            except Exception as e:
                print(f"Task processing error: {str(e)}")
                # Continue processing tasks even if one fails
                continue
    
    def on_closing(self):
        """Clean up resources before closing"""
        self.stop_camera()
        self.root.destroy()


if __name__ == "__main__":
    # Create and run the application
    root = tk.Tk()
    app = FaceAuthClientApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()