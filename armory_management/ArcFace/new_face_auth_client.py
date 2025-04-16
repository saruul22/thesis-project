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
import traceback

# Try to import QR code scanner
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None
    print("Warning: pyzbar not found. QR code scanning will be disabled.")
    print("Install with: pip install pyzbar")

# Try to import local ArcFace processor for offline mode
try:
    from local_arcface import LocalArcFaceProcessor
    OFFLINE_MODE_AVAILABLE = True
except ImportError:
    LocalArcFaceProcessor = None
    OFFLINE_MODE_AVAILABLE = False
    print("Info: local_arcface module not found. Offline mode will be disabled.")

# Setup error logging
LOG_FILE = "face_auth.log"

def log_message(message, level="INFO"):
    """Log a message to file"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            f.write(f"{timestamp} [{level}] {message}\n")
    except Exception as e:
        print(f"Warning: Could not write to log file: {str(e)}")

def log_error(message):
    """Log an error message with traceback"""
    log_message(message, level="ERROR")
    log_message(traceback.format_exc(), level="TRACEBACK")

# Main application class
class FaceAuthClientApp:
    def __init__(self, root):
        """Initialize the application with the given root window"""
        try:
            self.root = root
            self.root.title("Weapon System Authentication")
            self.root.geometry("1000x700")
            self.root.resizable(True, True)
            
            log_message("Initializing Face Authentication Client")
            
            # Load configuration
            self.config = self.load_config()
            
            # Set API endpoint
            self.api_base_url = self.config.get('api', 'base_url')
            self.api_token = self.config.get('api', 'token', fallback=None)
            
            # Initialize webcam variables
            self.cap = None
            self.is_capturing = False
            self.current_frame = None
            
            # Check offline mode
            self.offline_mode = self.config.getboolean('app', 'offline_mode', fallback=False)
            self.local_db_path = self.config.get('app', 'local_db_path', fallback='face_db')
            self.similarity_threshold = self.config.getfloat('app', 'similarity_threshold', fallback=0.6)
            
            # Initialize local face processor if in offline mode
            self.local_processor = None
            if self.offline_mode and OFFLINE_MODE_AVAILABLE:
                try:
                    self.local_processor = LocalArcFaceProcessor(models_dir=self.local_db_path)
                    log_message("Local ArcFace processor initialized")
                except Exception as e:
                    log_error(f"Failed to initialize local processor: {str(e)}")
                    messagebox.showwarning("Offline Mode", 
                        f"Failed to initialize local face recognition. Switching to online mode.\nError: {str(e)}")
                    self.offline_mode = False
            elif self.offline_mode:
                messagebox.showwarning("Offline Mode", 
                    "Local ArcFace processor not available. Please install dlib and its dependencies.")
                self.offline_mode = False
            
            # Status variables
            self.personnel_id = None
            self.verified = False
            self.qr_scanned = False
            self.qr_data = None
            self.face_detection_counter = 0
            self.is_processing_verification = False
            
            # Processing queue for background tasks
            self.task_queue = queue.Queue()
            self.worker_thread = threading.Thread(target=self.process_tasks, daemon=True)
            self.worker_thread.start()
            
            # Create the user interface
            self.create_ui()
            
            # Check connection
            self.check_connection()
            
            log_message("Application initialized successfully")
            
        except Exception as e:
            log_error(f"Error during initialization: {str(e)}")
            messagebox.showerror("Initialization Error", 
                                f"Error initializing application: {str(e)}\n\nSee log file for details.")
    
    def load_config(self):
        """Load configuration from config.ini file"""
        try:
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
                log_message("Configuration loaded from config.ini")
            else:
                # Save default config
                with open('config.ini', 'w') as f:
                    config.write(f)
                log_message("Default configuration created")
                    
            return config
        except Exception as e:
            log_error(f"Error loading configuration: {str(e)}")
            # Return default config
            config = configparser.ConfigParser()
            config['api'] = {'base_url': 'http://localhost:8000/api/face', 'token': ''}
            config['camera'] = {'device_id': '0', 'width': '640', 'height': '480'}
            config['app'] = {'offline_mode': 'false', 'local_db_path': 'face_db', 'similarity_threshold': '0.6'}
            return config
        
    def create_ui(self):
        """Create the user interface"""
        try:
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
            
            log_message("UI created successfully")
        except Exception as e:
            log_error(f"Error creating UI: {str(e)}")
            raise
    
    def setup_authentication_tab(self, parent):
        """Setup the unified authentication tab"""
        try:
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
            
            # Right panel (authentication info)
            right_panel = ttk.Frame(frame)
            right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10)
            
            # Transaction type selection
            transaction_frame = ttk.Frame(right_panel)
            transaction_frame.pack(fill=tk.X, pady=10)
            
            ttk.Label(transaction_frame, text="Mode:").pack(side=tk.LEFT)

            self.transaction_type = tk.StringVar(value="auto")
            self.transaction_mode_label = ttk.Label(transaction_frame, text="Auto (Detecting...)", foreground="blue")
            self.transaction_mode_label.pack(side=tk.LEFT, padx=10)
            
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
            
            log_message("Authentication tab setup complete")
        except Exception as e:
            log_error(f"Error setting up authentication tab: {str(e)}")
            raise
    
    def setup_register_tab(self, parent):
        """Setup the registration tab"""
        try:
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
            
            log_message("Registration tab setup complete")
        except Exception as e:
            log_error(f"Error setting up registration tab: {str(e)}")
            raise
    
    def setup_settings_tab(self, parent):
        """Setup the settings tab"""
        try:
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
            processor_status = "Available" if OFFLINE_MODE_AVAILABLE else "Not Available"
            ttk.Label(offline_frame, text=f"Local Processor: {processor_status}").grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=5)
            
            # Button to sync with server
            if OFFLINE_MODE_AVAILABLE:
                ttk.Button(offline_frame, text="Sync with Server", 
                         command=self.sync_with_server).grid(row=4, column=0, columnspan=2, pady=5)
            
            # Save button
            ttk.Button(frame, text="Save Settings", command=self.save_settings).pack(pady=10)
            
            # Test connection button
            ttk.Button(frame, text="Test Connection", command=self.check_connection).pack(pady=5)
            
            log_message("Settings tab setup complete")
        except Exception as e:
            log_error(f"Error setting up settings tab: {str(e)}")
            raise

    def save_settings(self):
        """Save settings to config file"""
        try:
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
                if new_offline_mode and OFFLINE_MODE_AVAILABLE:
                    try:
                        self.local_processor = LocalArcFaceProcessor(models_dir=self.local_db_path)
                        messagebox.showinfo("Offline Mode", "Local face processor initialized")
                    except Exception as e:
                        log_error(f"Failed to initialize local processor: {str(e)}")
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
            log_message("Settings saved")
            
            # Check connection with new settings if not in offline mode
            if not self.offline_mode:
                self.check_connection()
                
        except Exception as e:
            log_error(f"Error saving settings: {str(e)}")
            messagebox.showerror("Settings Error", f"Error saving settings: {str(e)}")
    
    def sync_with_server(self):
        """Synchronize local database with server"""
        if not OFFLINE_MODE_AVAILABLE or not self.local_processor:
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
        
        # Queue the sync task
        self.task_queue.put((self._sync_with_server_task, self.handle_sync_result))
    
    def _sync_with_server_task(self):
        """Background task for syncing with server"""
        try:
            log_message("Starting sync with server")
            
            # Set headers
            headers = {'Content-Type': 'application/json'}
            if self.api_token:
                headers['Authorization'] = f'Token {self.api_token}'
            
            # Get list of personnel with face records
            url = f"{self.api_base_url.rstrip('/')}/list_faces/"
            
            log_message(f"Getting face list from {url}")
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                log_error(f"Failed to retrieve face list: {response.text}")
                return {
                    'success': False,
                    'error': f"Failed to retrieve face list: {response.text}",
                    'status': "Sync failed"
                }
            
            personnel_list = response.json()
            log_message(f"Received {len(personnel_list.get('records', []))} face records")
            
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
            
            log_message(f"Sync complete. {success_count} records synchronized, {fail_count} failed.")
            return {
                'success': True,
                'message': f"Sync complete. {success_count} records synchronized, {fail_count} failed.",
                'status': "Sync complete"
            }
            
        except Exception as e:
            log_error(f"Error during sync: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'status': "Sync failed"
            }
    
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
            url = f"{self.api_base_url.rstrip('/')}/verify/"
            log_message(f"Checking connection to {url}")
            
            response = requests.get(url, timeout=3, headers=headers)
            
            if response.status_code in [200, 401, 403, 404]:  # Any of these means server is up
                self.connection_label.config(text="Connected", foreground="green")
                log_message("API connection successful")
                return True
            else:
                self.connection_label.config(text="Connection Error", foreground="red")
                log_message(f"API connection error: Status {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.connection_label.config(text="Connection Error", foreground="red")
            log_message(f"API connection error: {str(e)}")
            return False
        except Exception as e:
            log_error(f"Unexpected error checking connection: {str(e)}")
            self.connection_label.config(text="Error", foreground="red")
            return False
    
    def start_camera(self, canvas=None, mode=None):
        """Start the webcam feed"""
        try:
            log_message(f"Starting camera in {mode} mode")
            
            # Store the current mode
            self.current_mode = mode
            self.active_canvas = canvas
            
            # Reset states for authentication process if needed
            if mode == "authentication":
                self.qr_scanned = False
                self.qr_data = None
                self.personnel_id = None
                self.face_detection_counter = 0
                self.is_processing_verification = False
                self.qr_status_label.config(text="Step 1: Scan Weapon QR Code", foreground="black")
                