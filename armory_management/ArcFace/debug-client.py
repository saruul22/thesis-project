#!/usr/bin/env python3
import os
import sys
import traceback

print("Starting debug version of face authentication client...")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")

try:
    print("Importing required modules...")
    import cv2
    print(f"OpenCV version: {cv2.__version__}")
    
    import tkinter as tk
    print("Tkinter imported successfully")
    
    from tkinter import ttk, messagebox
    print("Tkinter submodules imported successfully")
    
    from PIL import Image, ImageTk
    print("PIL imported successfully")
    
    import numpy as np
    print("NumPy imported successfully")
    
    import requests
    print("Requests imported successfully")
    
    import queue
    import threading
    import configparser
    import base64
    from datetime import datetime
    print("Other standard libraries imported successfully")
    
    try:
        from pyzbar.pyzbar import decode as decode_qr
        print("PyZBar imported successfully")
    except ImportError:
        print("ERROR: PyZBar not found. Please install it with:")
        print("pip install pyzbar")
        sys.exit(1)
        
    # Try to load a face cascade to test OpenCV setup
    try:
        face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        print(f"Looking for face cascade at: {face_cascade_path}")
        if os.path.exists(face_cascade_path):
            face_cascade = cv2.CascadeClassifier(face_cascade_path)
            if face_cascade.empty():
                print("ERROR: Face cascade classifier loaded but is empty")
            else:
                print("Face cascade classifier loaded successfully")
        else:
            print("ERROR: Face cascade classifier file not found")
    except Exception as e:
        print(f"ERROR loading face cascade: {str(e)}")
    
    # Try to initialize webcam
    try:
        print("Testing webcam...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("ERROR: Could not open webcam. Check camera connections and permissions.")
        else:
            ret, frame = cap.read()
            if ret:
                print(f"Webcam test successful. Frame shape: {frame.shape}")
            else:
                print("ERROR: Could not read frame from webcam")
            cap.release()
    except Exception as e:
        print(f"ERROR during webcam test: {str(e)}")
    
    # Initialize GUI just to test
    try:
        print("Testing Tkinter...")
        root = tk.Tk()
        root.title("Debug Test")
        root.geometry("300x200")
        
        label = ttk.Label(root, text="If you see this window, Tkinter is working")
        label.pack(pady=20)
        
        button = ttk.Button(root, text="Close", command=root.destroy)
        button.pack()
        
        print("Starting Tkinter main loop...")
        print("Close the test window to continue...")
        root.mainloop()
        print("Tkinter test completed")
    except Exception as e:
        print(f"ERROR with Tkinter: {str(e)}")
    
    print("\nAll tests completed. If you see any ERROR messages above, address those issues.")
    print("If everything looks good, the original application should work.")
    
except Exception as e:
    print(f"A critical error occurred: {str(e)}")
    print("Detailed traceback:")
    traceback.print_exc()