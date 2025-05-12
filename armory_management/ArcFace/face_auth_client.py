import os
import sys
import cv2
import json
import base64
import cv2.data
import requests
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import configparser
from datetime import datetime
import threading
import queue
import math
from pyzbar.pyzbar import decode as decode_qr

# Import local ArcFace processor for offline mode
try:
    from local_arcface import LocalArcFaceProcessor
except ImportError:
    LocalArcFaceProcessor = None

class FaceAuthClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Галт зэвсгийн оролт, гаралтын бүртгэл")
        self.root.geometry("1000x700")
        self.root.resizable(True, True)
        
        # Setup style 
        self.setup_style()
        
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
        
        # Create header
        self.create_header(self.root)
        
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
        
        # Set up system tray
        self.setup_system_tray()
        
        # Check connection
        self.check_connection()
        
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
    
    def setup_style(self):
        """Set up custom styling for the application"""
        self.style = ttk.Style()

        # Try to use a modern theme if available
        try:
            self.style.theme_use('clam')  # 'clam' is generally available and looks more modern
        except tk.TclError:
            pass  # Fall back to default if 'clam' is not available
        
        # Define colors
        bg_color = "#f5f5f5"
        accent_color = "#3a7ebf"
        success_color = "#5cb85c"
        error_color = "#d9534f"
        warning_color = "#f0ad4e"

        # Configure general styles
        self.style.configure('TFrame', background=bg_color)
        self.style.configure('TLabel', background=bg_color, font=('Arial', 10))
        self.style.configure('TButton', font=('Arial', 10), padding=6)
        self.style.configure('TNotebook', background=bg_color)
        self.style.configure('TNotebook.Tab', padding=[10, 5], font=('Arial', 10))

        # Configure special styles
        self.style.configure('Title.TLabel', font=('Arial', 18, 'bold'))
        self.style.configure('Header.TLabel', font=('Arial', 12, 'bold'))
        self.style.configure('Success.TLabel', foreground=success_color)
        self.style.configure('Error.TLabel', foreground=error_color)
        self.style.configure('Warning.TLabel', foreground=warning_color)

        # Custom button styles
        self.style.configure('Primary.TButton', background=accent_color)
        self.style.configure('Success.TButton', background=success_color)
        self.style.configure('Danger.TButton', background=error_color)

        # Set window background
        self.root.configure(background=bg_color)

    def create_header(self, parent):
        """Create a header with logo and title"""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=10)

        # Create logo (you can replace with an actual logo image)
        logo_canvas = tk.Canvas(header_frame, width=60, height=60, bg="#f5f5f5", highlightthickness=0)
        logo_canvas.pack(side=tk.LEFT, padx=20)

        # Draw a simple logo
        logo_canvas.create_oval(5, 5, 55, 55, fill="#3a7ebf", outline="")
        logo_canvas.create_oval(15, 15, 45, 45, fill="#f5f5f5", outline="")
        logo_canvas.create_oval(25, 25, 35, 35, fill="#3a7ebf", outline="")

        # Add title
        title_frame = ttk.Frame(header_frame)
        title_frame.pack(side=tk.LEFT)

        ttk.Label(title_frame, text="Галт зэвсгийн", style='Title.TLabel').pack(anchor=tk.W)
        ttk.Label(title_frame, text="оролт, гаралтын бүртгэл", style='Title.TLabel').pack(anchor=tk.W)

        # Connection status indicator
        status_frame = ttk.Frame(header_frame)
        status_frame.pack(side=tk.RIGHT, padx=20)

        ttk.Label(status_frame, text="Холболт:").pack(side=tk.LEFT, padx=(0, 5))
        self.connection_label = ttk.Label(status_frame, text="Холбогдоогүй")
        self.connection_label.pack(side=tk.LEFT)

    def create_history_tab(self, parent):
        """Create a transaction history tab"""
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        # Create header for this tab
        header = ttk.Frame(frame)
        header.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(header, text="Transaction History", style='Header.TLabel').pack(side=tk.LEFT)

        # Refresh button
        refresh_btn = ttk.Button(header, text="Refresh", command=self.refresh_history)
        refresh_btn.pack(side=tk.RIGHT)

        # Add search field
        search_frame = ttk.Frame(frame)
        search_frame.pack(fill=tk.X, pady=5)

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<Return>", lambda e: self.search_history())

        ttk.Button(search_frame, text="Search", command=self.search_history).pack(side=tk.LEFT, padx=5)

        # Create treeview for transaction history
        self.history_tree = ttk.Treeview(frame, columns=("timestamp", "weapon", "personnel", "type", "status"))
        self.history_tree.pack(fill=tk.BOTH, expand=True, pady=5)

        # Configure columns
        self.history_tree.heading("#0", text="ID")
        self.history_tree.heading("timestamp", text="Timestamp")
        self.history_tree.heading("weapon", text="Weapon")
        self.history_tree.heading("personnel", text="Personnel")
        self.history_tree.heading("type", text="Type")
        self.history_tree.heading("status", text="Status")

        self.history_tree.column("#0", width=80)
        self.history_tree.column("timestamp", width=150)
        self.history_tree.column("weapon", width=150)
        self.history_tree.column("personnel", width=150)
        self.history_tree.column("type", width=100)
        self.history_tree.column("status", width=100)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.history_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        # Initially load history
        self.refresh_history()

    def refresh_history(self):
        """Refresh transaction history from server or local cache"""
        # Clear existing items
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        # Show processing indicator
        self.update_progress(10, "Loading history...")

        # Use a background thread to avoid freezing UI
        def load_history_task():
            try:
                # If offline, load from local cache
                if self.offline_mode:
                    # Example local cache (replace with actual implementation)
                    transactions = self.load_local_history()
                    return {
                        'success': True,
                        'transactions': transactions
                    }

                # Otherwise, get from server
                headers = {'Content-Type': 'application/json'}
                if self.api_token:
                    headers['Authorization'] = f'Token {self.api_token}'

                # Example API endpoint - adjust to match your backend
                url = f"{self.api_base_url.rstrip('/')}/transactions/history/"

                self.update_progress(30, "Requesting data...")

                response = requests.get(url, headers=headers, timeout=10)

                self.update_progress(70, "Processing data...")

                if response.status_code == 200:
                    result = response.json()
                    transactions = result.get('transactions', [])

                    # Save to local cache
                    self.save_local_history(transactions)

                    return {
                        'success': True,
                        'transactions': transactions
                    }
                else:
                    return {
                        'success': False,
                        'error': f"API Error: {response.text}"
                    }

            except Exception as e:
                return {
                    'success': False,
                    'error': str(e)
                }

        # Queue the task
        self.task_queue.put((load_history_task, self.handle_history_result))

    def handle_history_result(self, result):
        """Handle the history loading result"""
        if result['success']:
            transactions = result.get('transactions', [])

            # Add to treeview
            for tx in transactions:
                # Set row colors based on transaction type
                if tx.get('type') == 'checkout':
                    tag = 'checkout'
                elif tx.get('type') == 'checkin':
                    tag = 'checkin'
                else:
                    tag = 'other'

                # Add transaction to treeview
                self.history_tree.insert(
                    "", "end", text=tx.get('id', ''),
                    values=(
                        tx.get('timestamp', ''),
                        tx.get('weapon_info', {}).get('serial_number', 'Unknown'),
                        tx.get('personnel_info', {}).get('name', 'Unknown'),
                        tx.get('type', ''),
                        tx.get('status', '')
                    ),
                    tags=(tag,)
                )

            # Configure row colors
            self.history_tree.tag_configure('checkout', background='#ffeeee')
            self.history_tree.tag_configure('checkin', background='#eeffee')

            self.update_progress(100, f"Loaded {len(transactions)} transactions")

        else:
            messagebox.showerror("History Error", result['error'])
            self.update_progress(0, "Failed to load history")

        # Reset progress after a delay
        self.root.after(2000, lambda: self.update_progress(0, "Ready"))

    def search_history(self):
        """Search transaction history"""
        search_text = self.search_var.get().lower()

        # Clear highlighting
        for item in self.history_tree.get_children():
            self.history_tree.item(item, tags=self.history_tree.item(item, "tags"))

        if not search_text:
            return

        # Highlight matching items
        matched = []
        for item in self.history_tree.get_children():
            values = self.history_tree.item(item, "values")
            text = " ".join([str(v) for v in values]).lower()

            if search_text in text:
                matched.append(item)
                # Add 'match' tag while preserving original tag
                original_tags = self.history_tree.item(item, "tags")
                combined_tags = list(original_tags) + ["match"]
                self.history_tree.item(item, tags=combined_tags)

        # Configure matched row style
        self.history_tree.tag_configure('match', background='#ffffaa')

        # Select first match
        if matched:
            self.history_tree.selection_set(matched[0])
            self.history_tree.see(matched[0])
            self.update_progress(0, f"Found {len(matched)} matches")
        else:
            self.update_progress(0, "No matches found")

    def load_local_history(self):
        """Load transaction history from local cache file"""
        try:
            cache_file = os.path.join(self.local_db_path, 'transaction_history.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            print(f"Error loading local history: {e}")
            return []

    def save_local_history(self, transactions):
        """Save transaction history to local cache file"""
        try:
            os.makedirs(self.local_db_path, exist_ok=True)
            cache_file = os.path.join(self.local_db_path, 'transaction_history.json')
            with open(cache_file, 'w') as f:
                json.dump(transactions, f)
        except Exception as e:
            print(f"Error saving local history: {e}")

    def create_ui(self):
        """Create the UI elements"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="Галт зэвсгийн оролт, гаралтын бүртгэл", font=("Arial", 18, "bold"))
        title_label.pack(pady=10)
        
        # Create tabs
        tab_control = ttk.Notebook(main_frame)
        
        authentication_tab = ttk.Frame(tab_control)
        register_tab = ttk.Frame(tab_control)
        settings_tab = ttk.Frame(tab_control)
        
        tab_control.add(authentication_tab, text="Баталгаажуулалт")
        tab_control.add(register_tab, text="Царайны бүртгэл")
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
        """Setup the unified authentication tab with improved layout"""
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        # Create header for this tab
        header = ttk.Frame(frame)
        header.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(header, text="Баталгаажуулалт", style='Header.TLabel').pack(side=tk.LEFT)

        self.transaction_type = tk.StringVar(value="auto")
        mode_frame = ttk.Frame(header)
        mode_frame.pack(side=tk.RIGHT)

        ttk.Label(mode_frame, text="Горим:").pack(side=tk.LEFT)
        self.transaction_mode_label = ttk.Label(mode_frame, text="Автомат (Илрүүлж байна...)")
        self.transaction_mode_label.pack(side=tk.LEFT, padx=10)

        # Main content area
        content = ttk.Frame(frame)
        content.pack(fill=tk.BOTH, expand=True)

        # Left panel (camera feed)
        left_panel = ttk.Frame(content)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Camera container with border
        camera_container = ttk.LabelFrame(left_panel, text="Камер")
        camera_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Camera feed
        self.auth_canvas = tk.Canvas(camera_container, bg="black", width=640, height=480)
        self.auth_canvas.pack(pady=10, padx=10)

        # Camera controls
        camera_controls = ttk.Frame(left_panel)
        camera_controls.pack(pady=10, fill=tk.X)

        self.auth_start_btn = ttk.Button(camera_controls, text="Баталгаажуулалт Эхлүүлэх", 
                                        command=lambda: self.start_camera(canvas=self.auth_canvas, mode="authentication"),
                                        style="Primary.TButton")
        self.auth_start_btn.pack(side=tk.LEFT, padx=5)

        self.auth_stop_btn = ttk.Button(camera_controls, text="Зогсоох", 
                                        command=self.stop_camera, state=tk.DISABLED)
        self.auth_stop_btn.pack(side=tk.LEFT, padx=5)

        # Right panel (status and results)
        right_panel = ttk.Frame(content)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10, pady=10, expand=True)

        # Progress indicator
        progress_frame = ttk.LabelFrame(right_panel, text="Явц", padding=10)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        # QR status with icon
        qr_frame = ttk.Frame(progress_frame)
        qr_frame.pack(fill=tk.X, pady=5)

        self.qr_status_icon = ttk.Label(qr_frame, text="⭕")  # Circle icon
        self.qr_status_icon.pack(side=tk.LEFT, padx=(0, 10))

        self.qr_status_label = ttk.Label(qr_frame, text="1: QR код уншуулна", style='Header.TLabel')
        self.qr_status_label.pack(side=tk.LEFT)

        # Face verification status with icon
        face_frame = ttk.Frame(progress_frame)
        face_frame.pack(fill=tk.X, pady=5)

        self.face_status_icon = ttk.Label(face_frame, text="⭕")  # Circle icon
        self.face_status_icon.pack(side=tk.LEFT, padx=(0, 10))

        self.face_status_label = ttk.Label(face_frame, text="2: Царайны баталгаажуулалт (хүлээж байна)", style='Header.TLabel')
        self.face_status_label.pack(side=tk.LEFT)

        # Information panel
        info_frame = ttk.LabelFrame(right_panel, text="Мэдээлэл", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True)

        # Weapon info
        weapon_frame = ttk.Frame(info_frame)
        weapon_frame.pack(fill=tk.X, pady=5)

        ttk.Label(weapon_frame, text="Зэвсэг:", width=10).pack(side=tk.LEFT)
        self.weapon_info_label = ttk.Label(weapon_frame, text="QR уншигдаагүй байна")
        self.weapon_info_label.pack(side=tk.LEFT, padx=5)

        # Personnel info
        personnel_frame = ttk.Frame(info_frame)
        personnel_frame.pack(fill=tk.X, pady=5)

        ttk.Label(personnel_frame, text="Хүн:", width=10).pack(side=tk.LEFT)
        self.personnel_info_label = ttk.Label(personnel_frame, text="")
        self.personnel_info_label.pack(side=tk.LEFT, padx=5)

        # Face result
        face_result_frame = ttk.Frame(info_frame)
        face_result_frame.pack(fill=tk.X, pady=5)

        ttk.Label(face_result_frame, text="Итгэл:", width=10).pack(side=tk.LEFT)
        self.face_result_label = ttk.Label(face_result_frame, text="")
        self.face_result_label.pack(side=tk.LEFT, padx=5)

        # Final result
        result_frame = ttk.Frame(right_panel)
        result_frame.pack(fill=tk.X, pady=10)

        self.auth_result_label = ttk.Label(result_frame, text="", font=("Arial", 14, "bold"))
        self.auth_result_label.pack(pady=10, fill=tk.X)

        # Reset button
        self.auth_reset_btn = ttk.Button(right_panel, text="Дахин эхлүүлэх", 
                                       command=self.reset_authentication, state=tk.DISABLED)
        self.auth_reset_btn.pack(pady=10, fill=tk.X)
    
    def setup_register_tab(self, parent):
        """Setup the registration tab with improved styling"""
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Create header for this tab
        header = ttk.Frame(frame)
        header.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header, text="Царайны Бүртгэл", style='Header.TLabel').pack(side=tk.LEFT)
        
        # Main content area
        content = ttk.Frame(frame)
        content.pack(fill=tk.BOTH, expand=True)
        
        # Left panel (camera feed)
        left_panel = ttk.Frame(content)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Camera container with border
        camera_container = ttk.LabelFrame(left_panel, text="Камер")
        camera_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Camera feed
        self.register_canvas = tk.Canvas(camera_container, bg="black", width=640, height=480)
        self.register_canvas.pack(pady=10, padx=10)
        
        # Camera controls
        camera_controls = ttk.Frame(left_panel)
        camera_controls.pack(pady=10, fill=tk.X)
        
        self.reg_start_btn = ttk.Button(camera_controls, text="Камер Асаах", 
                                      command=lambda: self.start_camera(canvas=self.register_canvas, mode="register"),
                                      style="Primary.TButton")
        self.reg_start_btn.pack(side=tk.LEFT, padx=5)
        
        self.reg_stop_btn = ttk.Button(camera_controls, text="Зогсоох", 
                                     command=self.stop_camera, state=tk.DISABLED)
        self.reg_stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.reg_capture_btn = ttk.Button(camera_controls, text="Зураг Авах", 
                                        command=self.capture_registration_image, state=tk.DISABLED,
                                        style="Success.TButton")
        self.reg_capture_btn.pack(side=tk.LEFT, padx=5)
        
        # Right panel (registration info)
        right_panel = ttk.Frame(content)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10, pady=10, expand=True)
        
        # Registration form
        form_frame = ttk.LabelFrame(right_panel, text="Бүртгэлийн мэдээлэл", padding=10)
        form_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Personnel ID input
        reg_id_frame = ttk.Frame(form_frame)
        reg_id_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(reg_id_frame, text="Алба хаагчын дугаар:").pack(side=tk.LEFT)
        
        self.reg_id_var = tk.StringVar()
        reg_id_entry = ttk.Entry(reg_id_frame, textvariable=self.reg_id_var, width=20)
        reg_id_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Preview image (if captured)
        self.preview_frame = ttk.LabelFrame(right_panel, text="Урьдчилан харах", padding=10)
        self.preview_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.preview_label = ttk.Label(self.preview_frame, text="Зураг авна уу")
        self.preview_label.pack(pady=40, fill=tk.BOTH, expand=True)
        
        # Registration status
        status_frame = ttk.LabelFrame(right_panel, text="Бүртгэлийн төлөв", padding=10)
        status_frame.pack(fill=tk.X, pady=10)
        
        self.reg_status_label = ttk.Label(status_frame, text="Бүртгэгдээгүй", font=("Arial", 14))
        self.reg_status_label.pack(pady=10)
        
        self.reg_info_label = ttk.Label(status_frame, text="")
        self.reg_info_label.pack(pady=5)
        
        # Register button
        self.register_btn = ttk.Button(right_panel, text="Царай Бүртгэх", 
                                     command=self.register_face, state=tk.DISABLED,
                                     style="Primary.TButton")
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
            self.transaction_completed = False
            self.qr_status_label.config(text="Step 1: Scan Weapon QR Code", foreground="black")
            self.face_status_label.config(text="Step 2: Face Verification (waiting)", foreground="gray")
            self.weapon_info_label.config(text="No weapon scanned")
            self.personnel_info_label.config(text="")
            self.face_result_label.config(text="")
            self.auth_result_label.config(text="")
            # self.auth_capture_btn.config(state=tk.DISABLED)
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

    def show_processing_overlay(self, message="Processing..."):
        """Show a processing overlay on the currently active canvas"""
        if hasattr(self, 'active_canvas') and self.active_canvas:
            # Create a semi-transparent overlay
            self.active_canvas.create_rectangle(0, 0, 
                                             self.active_canvas.winfo_width(),
                                             self.active_canvas.winfo_height(),
                                             fill="black", stipple="gray50", tags="overlay")

            # Add processing text
            self.active_canvas.create_text(self.active_canvas.winfo_width() // 2,
                                        self.active_canvas.winfo_height() // 2,
                                        text=message,
                                        font=("Arial", 24, "bold"),
                                        fill="white", tags="overlay")

            # Add spinning animation
            self.spinner_angle = 0
            self.update_spinner()

    def update_spinner(self):
        """Update the spinner animation"""
        if hasattr(self, 'active_canvas') and self.active_canvas:
            # Check if overlay still exists
            if not self.active_canvas.find_withtag("overlay"):
                return

            # Clear previous spinner
            self.active_canvas.delete("spinner")

            # Calculate spinner position
            cx = self.active_canvas.winfo_width() // 2
            cy = (self.active_canvas.winfo_height() // 2) + 40
            r = 20

            # Draw spinner segments
            for i in range(8):
                angle = self.spinner_angle + (i * 45)
                rad = angle * 3.14159 / 180
                x1 = cx + int(r * 0.7 * math.cos(rad))
                y1 = cy + int(r * 0.7 * math.sin(rad))
                x2 = cx + int(r * math.cos(rad))
                y2 = cy + int(r * math.sin(rad))

                # Color fades based on position
                color = f"#{255-i*30:02x}{255-i*30:02x}{255-i*30:02x}"

                self.active_canvas.create_line(x1, y1, x2, y2, 
                                           fill=color, width=4, 
                                           tags="spinner")

            # Update angle
            self.spinner_angle = (self.spinner_angle + 10) % 360

            # Schedule next update
            self.root.after(50, self.update_spinner)

    def hide_processing_overlay(self):
        """Hide the processing overlay"""
        if hasattr(self, 'active_canvas') and self.active_canvas:
            self.active_canvas.delete("overlay")
            self.active_canvas.delete("spinner")

    def show_result_effect(self, success=True):
        """Show an animated success or failure effect on the canvas"""
        if hasattr(self, 'active_canvas') and self.active_canvas:
            # Create a semi-transparent overlay
            overlay_color = "#00ff00" if success else "#ff0000"
            self.active_canvas.create_rectangle(0, 0, 
                                             self.active_canvas.winfo_width(),
                                             self.active_canvas.winfo_height(),
                                             fill=overlay_color, stipple="gray25", tags="result_effect")

            # Add result text
            text = "SUCCESS" if success else "FAILED"
            self.active_canvas.create_text(self.active_canvas.winfo_width() // 2,
                                        self.active_canvas.winfo_height() // 2,
                                        text=text,
                                        font=("Arial", 36, "bold"),
                                        fill="white", tags="result_effect")

            # Schedule removal
            self.root.after(1500, lambda: self.active_canvas.delete("result_effect"))

    def setup_system_tray(self):
        """Set up system tray icon and menu"""
        try:
            # Try to import required libraries
            import pystray
            from PIL import Image, ImageDraw

            # Create system tray icon image
            icon_size = 64
            icon_image = Image.new('RGB', (icon_size, icon_size), color=(54, 66, 86))
            draw = ImageDraw.Draw(icon_image)

            # Draw a simple face outline
            margin = 10
            draw.ellipse([margin, margin, icon_size-margin, icon_size-margin], 
                        fill=(255, 255, 255))
            # Eyes
            eye_margin = icon_size // 4
            eye_size = icon_size // 10
            draw.ellipse([eye_margin, eye_margin, eye_margin+eye_size, eye_margin+eye_size], 
                        fill=(54, 66, 86))
            draw.ellipse([icon_size-eye_margin-eye_size, eye_margin, 
                         icon_size-eye_margin, eye_margin+eye_size], 
                        fill=(54, 66, 86))

            # Menu items
            def show_window(icon, item):
                self.root.deiconify()
                self.root.lift()

            def exit_app(icon, item):
                icon.stop()
                self.on_closing()

            # Create menu
            menu = (
                pystray.MenuItem('Show', show_window),
                pystray.MenuItem('Exit', exit_app)
            )

            # Create icon
            self.tray_icon = pystray.Icon("faceauth", icon_image, "Face Auth Client", menu)

            # Run in a separate thread
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

            # Override close button to minimize to tray
            self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

        except ImportError:
            # Fall back to normal close behavior if pystray is not available
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            
    def minimize_to_tray(self):
        """Minimize application to system tray"""
        self.root.withdraw()
        # Optional: show notification
        if hasattr(self, 'tray_icon'):
            self.tray_icon.notify("Face Auth Client is still running in the background.")

    def update_qr_status(self, scanned=False, message=None):
        """Update QR status with visual indicator"""
        if scanned:
            self.qr_status_icon.config(text="✅")
            self.qr_status_label.config(text="1: QR Код Уншигдлаа ✓", style="Success.TLabel")
        else:
            self.qr_status_icon.config(text="⭕")
            if message:
                self.qr_status_label.config(text=f"1: {message}", style="Header.TLabel")
            else:
                self.qr_status_label.config(text="1: QR код уншуулна", style="Header.TLabel")

    def update_face_status(self, status, message=None):
        """Update face verification status with visual indicator"""
        if status == "success":
            self.face_status_icon.config(text="✅")
            self.face_status_label.config(text="2: Царайны Баталгаажуулалт Амжилттай ✓", style="Success.TLabel")
        elif status == "error":
            self.face_status_icon.config(text="❌")
            self.face_status_label.config(text=f"2: Алдаа: {message}", style="Error.TLabel")
        elif status == "waiting":
            self.face_status_icon.config(text="⭕")
            self.face_status_label.config(text="2: Царайны Баталгаажуулалт (хүлээж байна)", foreground="gray")
        elif status == "processing":
            self.face_status_icon.config(text="⏳")
            self.face_status_label.config(text="2: Баталгаажуулж байна...", foreground="blue")
        else:
            self.face_status_icon.config(text="⭕")
            if message:
                self.face_status_label.config(text=f"2: {message}", style="Header.TLabel")
            else:
                self.face_status_label.config(text="2: Царайны Баталгаажуулалт", style="Header.TLabel")
    
    def update_camera(self):
        """Update the camera feed on the canvas with improved face detection visualization"""
        if self.is_capturing and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # Store the original frame
                self.current_frame = frame.copy()
                
                # Handle different modes
                if hasattr(self, 'current_mode') and self.current_mode == "authentication":
                    if not self.qr_scanned:
                        # In QR scanning mode - process QR codes
                        qr_codes = decode_qr(frame)
                        if qr_codes:
                            for qr in qr_codes:
                                # Draw enhanced QR detection
                                points = qr.polygon
                                if len(points) > 4:
                                    hull = cv2.convexHull(
                                        np.array([(p.x, p.y) for p in points], dtype=np.int32))
                                    cv2.polylines(frame, [hull], True, (0, 255, 0), 3)
                                    # Add a highlight effect
                                    overlay = frame.copy()
                                    cv2.fillPoly(overlay, [hull], (0, 255, 0, 128))
                                    cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                                else:
                                    points_array = np.array([(p.x, p.y) for p in points], dtype=np.int32)
                                    cv2.polylines(frame, [points_array], True, (0, 255, 0), 3)
                                    # Add a highlight effect
                                    overlay = frame.copy()
                                    cv2.fillPoly(overlay, [points_array], (0, 255, 0, 128))
                                    cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                                
                                # Add a text label
                                cv2.putText(frame, "QR Code Detected", (points[0].x, points[0].y - 10),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                                
                                # Process QR data
                                self.qr_data = qr.data.decode('utf-8')
                                self.qr_scanned = True
                                self.update_qr_status(scanned=True)
                                
                                # Get weapon and personnel info from server
                                self.get_weapon_and_personnel_info(self.qr_data)
    
                    elif self.personnel_id and not hasattr(self, 'verification_in_progress') and not self.transaction_completed:
                        # Initialize frame counter if not exists
                        if not hasattr(self, 'frame_counter'):
                            self.frame_counter = 0
                        self.frame_counter += 1
    
                        # Only run face detection every 2nd frame for efficiency
                        if self.frame_counter % 2 == 0:
                            # Create a smaller version of the frame for faster processing
                            frame_small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    
                            # Convert to grayscale for face detection
                            gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
    
                            # Use a face cascade classifier
                            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    
                            # Scale coordinates back up and draw rectangles around the faces
                            for (x, y, w, h) in faces:
                                # Scale coordinates back to original size
                                x2, y2, w2, h2 = int(x*2), int(y*2), int(w*2), int(h*2)
                                
                                # Draw a nice looking rectangle
                                cv2.rectangle(frame, (x2, y2), (x2+w2, y2+h2), (0, 255, 255), 2)
                                
                                # Draw corner markers for visual appeal
                                marker_length = 20
                                # Top left
                                cv2.line(frame, (x2, y2), (x2 + marker_length, y2), (0, 255, 255), 3)
                                cv2.line(frame, (x2, y2), (x2, y2 + marker_length), (0, 255, 255), 3)
                                # Top right
                                cv2.line(frame, (x2 + w2, y2), (x2 + w2 - marker_length, y2), (0, 255, 255), 3)
                                cv2.line(frame, (x2 + w2, y2), (x2 + w2, y2 + marker_length), (0, 255, 255), 3)
                                # Bottom left
                                cv2.line(frame, (x2, y2 + h2), (x2 + marker_length, y2 + h2), (0, 255, 255), 3)
                                cv2.line(frame, (x2, y2 + h2), (x2, y2 + h2 - marker_length), (0, 255, 255), 3)
                                # Bottom right
                                cv2.line(frame, (x2 + w2, y2 + h2), (x2 + w2 - marker_length, y2 + h2), (0, 255, 255), 3)
                                cv2.line(frame, (x2 + w2, y2 + h2), (x2 + w2, y2 + h2 - marker_length), (0, 255, 255), 3)
    
                            # If we detect exactly one face that's large enough (close to camera)
                            if len(faces) == 1 and faces[0][2] > 50 and faces[0][3] > 50:
                                # Draw a thicker rectangle to indicate "ready to capture"
                                (x, y, w, h) = faces[0]
                                # Scale coordinates back to original size
                                x2, y2, w2, h2 = int(x*2), int(y*2), int(w*2), int(h*2)
                                
                                # Draw a nice looking rectangle
                                cv2.rectangle(frame, (x2, y2), (x2+w2, y2+h2), (0, 255, 0), 3)
                                
                                # Draw corner markers for visual appeal
                                marker_length = 20
                                # Top left
                                cv2.line(frame, (x2, y2), (x2 + marker_length, y2), (0, 255, 0), 4)
                                cv2.line(frame, (x2, y2), (x2, y2 + marker_length), (0, 255, 0), 4)
                                # Top right
                                cv2.line(frame, (x2 + w2, y2), (x2 + w2 - marker_length, y2), (0, 255, 0), 4)
                                cv2.line(frame, (x2 + w2, y2), (x2 + w2, y2 + marker_length), (0, 255, 0), 4)
                                # Bottom left
                                cv2.line(frame, (x2, y2 + h2), (x2 + marker_length, y2 + h2), (0, 255, 0), 4)
                                cv2.line(frame, (x2, y2 + h2), (x2, y2 + h2 - marker_length), (0, 255, 0), 4)
                                # Bottom right
                                cv2.line(frame, (x2 + w2, y2 + h2), (x2 + w2 - marker_length, y2 + h2), (0, 255, 0), 4)
                                cv2.line(frame, (x2 + w2, y2 + h2), (x2 + w2, y2 + h2 - marker_length), (0, 255, 0), 4)
                                
                                # Add text below the face
                                cv2.putText(frame, "Face Detected", (x2, y2 + h2 + 25),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    
                                # Count frames with a face detected (for stability)
                                if not hasattr(self, 'face_detection_counter'):
                                    self.face_detection_counter = 0
                                self.face_detection_counter += 1
    
                                # After detecting a stable face for multiple frames, auto-capture
                                if self.face_detection_counter > 3:
                                    # Set a flag to prevent multiple simultaneous verifications
                                    self.verification_in_progress = True
    
                                    # Auto-capture and verify
                                    self.captured_frame = self.current_frame.copy()
                                    self.update_face_status("processing", "Баталгаажуулж байна...")
    
                                    # Proceed to verification (run in a separate thread)
                                    threading.Thread(
                                        target=self.run_face_verification,
                                        daemon=True
                                    ).start()
                                    
                                    # Add a capture effect
                                    cv2.rectangle(frame, (0, 0), (frame.shape[1], frame.shape[0]), (0, 255, 0), 10)
                            else:
                                # Reset counter if no face or multiple faces
                                if hasattr(self, 'face_detection_counter'):
                                    self.face_detection_counter = 0
            
                elif hasattr(self, 'current_mode') and self.current_mode == "register":
                    # For registration mode, also show face detection
                    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

                    for (x, y, w, h) in faces:
                        # Draw a rectangle with a 3D effect
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 255), 2)

                        # Draw corner markers
                        marker_length = 20
                        # Top left
                        cv2.line(frame, (x, y), (x + marker_length, y), (0, 255, 255), 3)
                        cv2.line(frame, (x, y), (x, y + marker_length), (0, 255, 255), 3)
                        # Top right
                        cv2.line(frame, (x + w, y), (x + w - marker_length, y), (0, 255, 255), 3)
                        cv2.line(frame, (x + w, y), (x + w, y + marker_length), (0, 255, 255), 3)
                        # Bottom left
                        cv2.line(frame, (x, y + h), (x + marker_length, y + h), (0, 255, 255), 3)
                        cv2.line(frame, (x, y + h), (x, y + h - marker_length), (0, 255, 255), 3)
                        # Bottom right
                        cv2.line(frame, (x + w, y + h), (x + w - marker_length, y + h), (0, 255, 255), 3)
                        cv2.line(frame, (x + w, y + h), (x + w, y + h - marker_length), (0, 255, 255), 3)

                        # Label
                        cv2.putText(frame, "Face Detected", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                # Convert to RGB for tkinter and update canvas
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
                # self.auth_capture_btn.config(state=tk.DISABLED)
                self.reg_start_btn.config(state=tk.NORMAL)
            elif self.current_mode == "register":
                self.reg_start_btn.config(state=tk.NORMAL)
                self.reg_stop_btn.config(state=tk.DISABLED)
                self.reg_capture_btn.config(state=tk.DISABLED)
                self.register_btn.config(state=tk.DISABLED)
                self.auth_start_btn.config(state=tk.NORMAL)
        
        self.status_label.config(text="Camera stopped")
    
    def get_weapon_and_personnel_info(self, qr_data):
        """Get weapon information and automatically determine transaction type"""
        try:
            # Prepare headers
            headers = {'Content-Type': 'application/json'}
            if self.api_token:
                headers['Authorization'] = f'Token {self.api_token}'
            
            # Send request to your server
            url = f"{self.api_base_url.rstrip('/')}/weapon/info/"
            response = requests.post(
                url,
                json={"qr_code": qr_data, "auto_detect": True},
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

                # Get current location and set transaction type
                location = weapon_info.get('location', 'unknown')
                recommended_action = result.get('recommended_action')

                if location == 'armory':
                    self.transaction_type.set('check_out')
                    self.transaction_mode_label.config(text="CHECK OUT (In Armory)", foreground="blue")
                elif location == 'field':
                    self.transaction_type.set('check_in')
                    self.transaction_mode_label.config(text="CHECK IN (In Field)", foreground="green")
                else:
                    self.transaction_type.set('check_in' if recommended_action == 'checkin' else 'checkout')
                    self.transaction_mode_label.config(text=f"AUTO ({recommended_action.upper()})", foreground="purple")
                
                # Store and display personnel info
                self.personnel_id = result.get('personnel_id')
                personnel_info = result.get('personnel_info', {})
                
                if self.personnel_id:
                    self.personnel_info_label.config(
                        text=f"Personnel: {personnel_info.get('rank', '')} {personnel_info.get('name', 'Unknown')} ({self.personnel_id})"
                    )
                    self.face_status_label.config(text="Step 2: Face Verification (active)", foreground="black")
                    # Enable capture button now that we have a personnel ID
                    # self.auth_capture_btn.config(state=tk.NORMAL)
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
                            # self.auth_capture_btn.config(state=tk.NORMAL)
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
        # self.auth_capture_btn.config(state=tk.DISABLED)
        self.verify_face_for_transaction(self.personnel_id, self.captured_frame, self.qr_data)
    
    def verify_face_for_transaction(self, personnel_id, frame, qr_data):
        """Verify face and complete transaction with auto-reset"""
        try:
            # Compress image before sending to reduce data size
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70] # Lower quality = smaller size
            _, buffer = cv2.imencode('.jpg',frame, encode_param)

            # Convert to base64
            img_base64 = base64.b64encode(buffer).decode('utf-8')

            # Log info for debugging
            print(f"Starting verification for personnel ID: {personnel_id}")
            print(f"Transaction type: {self.transaction_type.get()}")
            print(f"QR data length: {len(qr_data)}")

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
            print(f"Sending request to: {url}")

            # Update status
            self.status_label.config(text="Processing transaction...")
            self.face_status_label.config(text="Step 2: Verifying face...", foreground="blue")

            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                print(f"Response data: {result}")

                if result.get('verified', False):
                    self.face_status_label.config(text="Step 2: Face Verified ✓", foreground="green")
                    self.face_result_label.config(text=f"Confidence: {result.get('confidence', 0) * 100:.2f}%")

                    # Display transaction result
                    if result.get('transaction_success', False):
                        transaction_type = "CHECK-IN" if self.transaction_type.get() == 'check_in' else "CHECK-OUT"
                        self.auth_result_label.config(text=f"{transaction_type} SUCCESSFUL", foreground="green")

                        # Schedule auto-reset after successful transaction
                        self.root.after(3000, self.auto_reset_for_next_transaction)
                        self.transaction_completed = True
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
                error_text = response.text
                print(f"Error response: {error_text}")
                self.face_status_label.config(text="Step 2: Verification Error ✗", foreground="red")
                self.auth_result_label.config(text=f"TRANSACTION FAILED: Server error {response.status_code}", foreground="red")
                # Enable reset button for failed transactions
                self.auth_reset_btn.config(state=tk.NORMAL)

        except Exception as e:
            print(f"Exception during verification: {str(e)}")
            self.face_status_label.config(text="Step 2: Verification Error ✗", foreground="red")
            self.auth_result_label.config(text=f"TRANSACTION FAILED: {str(e)}", foreground="red")
            # Enable reset button for failed transactions
            self.auth_reset_btn.config(state=tk.NORMAL)

        self.status_label.config(text="Transaction complete")
    
    def reset_authentication(self):
        """Reset the authentication process"""
        self.qr_scanned = False
        self.qr_data = None
        self.personnel_id = None
        self.transaction_completed = False
        
        self.qr_status_label.config(text="Step 1: Scan Weapon QR Code", foreground="black")
        self.weapon_info_label.config(text="No weapon scanned")
        self.personnel_info_label.config(text="")
        self.face_status_label.config(text="Step 2: Face Verification (waiting)", foreground="gray")
        self.face_result_label.config(text="")
        self.auth_result_label.config(text="")
        
        # self.auth_capture_btn.config(state=tk.DISABLED)
        self.auth_reset_btn.config(state=tk.DISABLED)
        
        self.status_label.config(text="Authentication reset")
    
    def capture_registration_image(self):
        """Capture image for registration with preview"""
        if not hasattr(self, 'current_frame') or self.current_frame is None:
            messagebox.showerror("Error", "No frame to capture")
            return

        # Store captured frame
        self.captured_frame = self.current_frame.copy()

        # Display preview
        preview_img = cv2.resize(self.captured_frame, (200, 150))
        preview_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
        preview_image = Image.fromarray(preview_rgb)
        preview_photo = ImageTk.PhotoImage(image=preview_image)

        # Update preview
        if hasattr(self, 'preview_label'):
            self.preview_label.config(image=preview_photo)
            self.preview_label.image = preview_photo  # Keep a reference

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

    def run_face_verification(self):
        """Run face verification in a separate thread and handle the state properly"""
        try:
            # Run the verification
            self.verify_face_for_transaction(
                self.personnel_id,
                self.captured_frame,
                self.qr_data
            )
        finally:
            # Reset verification state when done
            self.face_detection_counter = 0
            if hasattr(self, 'verification_in_progress'):
                delattr(self, 'verification_in_progress')

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

    def setup_language_selector(self):
        """Set up language selector in settings tab"""
        language_frame = ttk.LabelFrame(self.settings_tab, text="Language Settings")
        language_frame.pack(fill=tk.X, pady=10, padx=10)

        self.language_var = tk.StringVar(value="mn")  # Default is Mongolian

        # Language options
        ttk.Radiobutton(language_frame, text="Монгол", variable=self.language_var, 
                       value="mn", command=self.update_language).grid(row=0, column=0, padx=5, pady=5)
        ttk.Radiobutton(language_frame, text="English", variable=self.language_var, 
                       value="en", command=self.update_language).grid(row=0, column=1, padx=5, pady=5)

    def update_language(self):
        """Update UI language based on selection"""
        lang = self.language_var.get()

        # Define translations
        translations = {
            "mn": {
                "title": "Галт зэвсгийн оролт, гаралтын бүртгэл",
                "auth_tab": "Баталгаажуулалт",
                "register_tab": "Царайны бүртгэл",
                "settings_tab": "Тохиргоо",
                "start_auth": "Баталгаажуулалт Эхлүүлэх",
                "stop": "Зогсоох",
                "mode": "Горим:",
                "auto_mode": "Автомат (Илрүүлж байна...)",
                "step1": "1: QR код уншуулна",
                "step2": "2: Царайны баталгаажуулалт (хүлээж байна)",
                "no_weapon": "QR уншигдаагүй байна",
                "weapon": "Зэвсэг:",
                "person": "Хүн:",
                "confidence": "Итгэл:",
                "reset": "Дахин эхлүүлэх",
                # ... add more translations as needed
            },
            "en": {
                "title": "Weapon Check-in/Check-out System",
                "auth_tab": "Authentication",
                "register_tab": "Face Registration",
                "settings_tab": "Settings",
                "start_auth": "Start Authentication",
                "stop": "Stop",
                "mode": "Mode:",
                "auto_mode": "Auto (Detecting...)",
                "step1": "1: Scan QR Code",
                "step2": "2: Face Verification (waiting)",
                "no_weapon": "No weapon scanned",
                "weapon": "Weapon:",
                "person": "Person:",
                "confidence": "Confidence:",
                "reset": "Reset",
                # ... add more translations as needed
            }
        }

        # Update UI elements with selected language
        t = translations.get(lang, translations["en"])  # Fallback to English

        # Update window title
        self.root.title(t["title"])

        # Update tab names
        if hasattr(self, 'tab_control'):
            self.tab_control.tab(0, text=t["auth_tab"])
            self.tab_control.tab(1, text=t["register_tab"])
            self.tab_control.tab(2, text=t["settings_tab"])

        # Update buttons
        if hasattr(self, 'auth_start_btn'):
            self.auth_start_btn.config(text=t["start_auth"])
        if hasattr(self, 'auth_stop_btn'):
            self.auth_stop_btn.config(text=t["stop"])

        # Continue updating other UI elements...
        # This is just a starting example
    def setup_appearance_selector(self):
        """Set up appearance/theme selector in settings tab"""
        appearance_frame = ttk.LabelFrame(self.settings_tab, text="Appearance")
        appearance_frame.pack(fill=tk.X, pady=10, padx=10)

        self.theme_var = tk.StringVar(value="light")  # Default is light mode

        # Theme options
        ttk.Radiobutton(appearance_frame, text="Light Mode", variable=self.theme_var, 
                       value="light", command=self.update_theme).grid(row=0, column=0, padx=5, pady=5)
        ttk.Radiobutton(appearance_frame, text="Dark Mode", variable=self.theme_var, 
                       value="dark", command=self.update_theme).grid(row=0, column=1, padx=5, pady=5)

    def update_theme(self):
        """Update application theme based on selection"""
        theme = self.theme_var.get()

        if theme == "dark":
            # Dark theme colors
            bg_color = "#333333"
            fg_color = "#ffffff"
            accent_color = "#007acc"
            success_color = "#5cb85c"
            error_color = "#d9534f"
            warning_color = "#f0ad4e"

            # Update canvas backgrounds
            if hasattr(self, 'auth_canvas'):
                self.auth_canvas.config(bg="#1e1e1e")
            if hasattr(self, 'register_canvas'):
                self.register_canvas.config(bg="#1e1e1e")

            # Update window background
            self.root.configure(background=bg_color)

            # Try to configure ttk styles for dark mode
            try:
                self.style.configure('TFrame', background=bg_color)
                self.style.configure('TLabel', background=bg_color, foreground=fg_color)
                self.style.configure('TButton', background=accent_color)
                self.style.configure('TNotebook', background=bg_color, foreground=fg_color)

                # Configure special styles
                self.style.configure('Title.TLabel', background=bg_color, foreground=fg_color)
                self.style.configure('Header.TLabel', background=bg_color, foreground=fg_color)
                self.style.configure('Success.TLabel', foreground=success_color)
                self.style.configure('Error.TLabel', foreground=error_color)
                self.style.configure('Warning.TLabel', foreground=warning_color)

                # Custom button styles for dark mode
                self.style.configure('Primary.TButton', background=accent_color)
                self.style.configure('Success.TButton', background=success_color)
                self.style.configure('Danger.TButton', background=error_color)

            except Exception as e:
                print(f"Error configuring dark theme: {e}")

        else:
            # Light theme (default) colors
            bg_color = "#f5f5f5"
            fg_color = "#000000"
            accent_color = "#3a7ebf"
            success_color = "#5cb85c"
            error_color = "#d9534f"
            warning_color = "#f0ad4e"

            # Update canvas backgrounds
            if hasattr(self, 'auth_canvas'):
                self.auth_canvas.config(bg="black")
            if hasattr(self, 'register_canvas'):
                self.register_canvas.config(bg="black")

            # Update window background
            self.root.configure(background=bg_color)

            # Try to configure ttk styles for light mode
            try:
                self.style.configure('TFrame', background=bg_color)
                self.style.configure('TLabel', background=bg_color, foreground=fg_color)
                self.style.configure('TButton', background=accent_color)
                self.style.configure('TNotebook', background=bg_color, foreground=fg_color)

                # Configure special styles
                self.style.configure('Title.TLabel', background=bg_color, foreground=fg_color)
                self.style.configure('Header.TLabel', background=bg_color, foreground=fg_color)
                self.style.configure('Success.TLabel', foreground=success_color)
                self.style.configure('Error.TLabel', foreground=error_color)
                self.style.configure('Warning.TLabel', foreground=warning_color)

                # Custom button styles for light mode
                self.style.configure('Primary.TButton', background=accent_color)
                self.style.configure('Success.TButton', background=success_color)
                self.style.configure('Danger.TButton', background=error_color)

            except Exception as e:
                print(f"Error configuring light theme: {e}")

    def create_progress_bar(self, parent, initial_text="Ready"):
        """Create a progress bar with text label"""
        frame = ttk.Frame(parent)
        
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(frame, variable=self.progress_var, length=300)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.progress_label = ttk.Label(frame, text=initial_text)
        self.progress_label.pack(side=tk.RIGHT)
        
        return frame
    
    def update_progress(self, value=0, text=None):
        """Update progress bar value and text"""
        if hasattr(self, 'progress_var'):
            self.progress_var.set(value)
        
        if text and hasattr(self, 'progress_label'):
            self.progress_label.config(text=text)
            
        # Process pending events to show updates
        self.root.update_idletasks()

if __name__ == "__main__":
    # Create and run the application
    root = tk.Tk()
    app = FaceAuthClientApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

class ToolTip:
    """Create a tooltip for a given widget"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
        
    def show_tooltip(self, event=None):
        # Get widget position
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        # Create tooltip window
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        
        # Create tooltip content
        frame = ttk.Frame(self.tooltip, borderwidth=1, relief="solid")
        frame.pack(fill=tk.BOTH, expand=True)
        
        label = ttk.Label(frame, text=self.text, wraplength=250,
                         justify="left", background="#ffffe0", 
                         relief="solid", borderwidth=0)
        label.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        
    def hide_tooltip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None