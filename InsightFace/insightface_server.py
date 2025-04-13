from flask import Flask, request, jsonify
import insightface
import numpy as np
import cv2
import base64
import io

app = Flask(__name__)

# Load InsightFace model
model = insightface.app.FaceAnalysis(providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
model.prepare(ctx_id=0, det_size=(640, 640))

@app.route('/api/detect', methods=['POST'])
def detect_faces():
    data = request.json
    img_data = base64.b64decode(data['image'])
    img = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
    
    faces = model.get(img)
    results = []
    
    for face in faces[:int(data.get('max_faces', 1))]:
        # Fix this line to handle None values properly
        landmarks = face.landmark.tolist() if (hasattr(face, 'landmark') and face.landmark is not None) else None
        
        results.append({
            'bbox': face.bbox.tolist(),
            'landmarks': landmarks,
            'score': float(face.det_score)
        })
    
    return jsonify({"faces": results})

@app.route('/api/extract_embeddings', methods=['POST'])
def extract_embeddings():
    data = request.json
    img_data = base64.b64decode(data['image'])
    img = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
    
    faces = model.get(img)
    if not faces:
        return jsonify({"error": "No face detected"})
    
    # Get the largest face
    face = max(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
    embedding = face.embedding
    
    # Convert embedding to base64
    embedding_bytes = embedding.astype(np.float32).tobytes()
    embedding_b64 = base64.b64encode(embedding_bytes).decode('utf-8')
    
    return jsonify({
        "embeddings": embedding_b64,
        "status": "SUCCESS"
    })

@app.route('/api/compare', methods=['POST'])
def compare_embeddings():
    data = request.json
    
    # Decode embeddings
    emb1_bytes = base64.b64decode(data['embedding1'])
    emb2_bytes = base64.b64decode(data['embedding2'])
    
    emb1 = np.frombuffer(emb1_bytes, dtype=np.float32)
    emb2 = np.frombuffer(emb2_bytes, dtype=np.float32)
    
    # Normalize embeddings
    emb1 = emb1 / np.linalg.norm(emb1)
    emb2 = emb2 / np.linalg.norm(emb2)
    
    # Calculate similarity
    similarity = np.dot(emb1, emb2)
    
    return jsonify({
        "similarity": float(similarity),
        "status": "SUCCESS"
    })

@app.route('/test', methods=['GET'])
def test():
    return jsonify({"status": "working"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)