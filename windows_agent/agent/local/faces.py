from __future__ import annotations

import base64
import hashlib
import io
import json
import threading
from pathlib import Path

import numpy as np

DETECTOR = 'face_detection_yunet_2026may.onnx'
RECOGNIZER = 'face_recognition_sface_2021dec.onnx'
PINNED_HASHES = {
    DETECTOR: 'ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0',
    RECOGNIZER: '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79',
}


class LocalFaceEngine:
    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = threading.Lock()
        self.detector = None
        self.recognizer = None
        self.status = {'available': False, 'model': 'OpenCV YuNet + SFace', 'provider': 'CPU', 'field_accuracy_verified': False, 'error': 'Models not yet checked', 'liveness': False}

    def initialize(self):
        with self.lock:
            self._load()
        return dict(self.status)

    def _load(self):
        if self.detector is not None and self.recognizer is not None:
            return
        try:
            import cv2
            manifest = json.loads((self.directory / 'face-manifest.json').read_text(encoding='utf-8'))
            if manifest['version'] != 1:
                raise ValueError('Unsupported face model manifest')
            for filename in (DETECTOR, RECOGNIZER):
                path = self.directory / filename
                with path.open('rb') as source:
                    digest = hashlib.file_digest(source, 'sha256').hexdigest()
                if digest != PINNED_HASHES[filename] or digest != manifest['models'][filename]['sha256'] or not (self.directory / manifest['models'][filename]['license_file']).is_file():
                    raise ValueError('Face model integrity or license notice missing')
            detector = cv2.FaceDetectorYN.create(str(self.directory / DETECTOR), '', (320, 320), 0.9, 0.3, 1000)
            recognizer = cv2.FaceRecognizerSF.create(str(self.directory / RECOGNIZER), '')
            detector.detect(np.zeros((320, 320, 3), np.uint8))
            feature = recognizer.feature(np.zeros((112, 112, 3), np.uint8))
            if feature.size != 128 or not np.isfinite(feature).all():
                raise ValueError('Face runtime output is invalid')
            self.detector, self.recognizer = detector, recognizer
            self.status.update(available=True, error='', integrity_verified=True)
        except Exception as exc:
            self.status.update(available=False, error=f'Local face models unavailable: {type(exc).__name__}. Use a package containing verified YuNet and SFace models.')
            raise ValueError(self.status['error']) from exc

    def template(self, photo) -> np.ndarray:
        import cv2
        if isinstance(photo, str):
            from PIL import Image
            if len(photo) > 2800000:
                raise ValueError('Use a photo under 2 MB')
            raw = base64.b64decode(photo.split(',')[-1], validate=True)
            try:
                with Image.open(io.BytesIO(raw)) as header:
                    if header.width > 4096 or header.height > 4096 or header.width * header.height > 12000000:
                        raise ValueError('Photo dimensions are too large; use at most 4096 pixels per side and 12 megapixels')
            except (OSError, Image.DecompressionBombError) as exc:
                raise ValueError('Use a valid JPG, PNG or WebP face photo') from exc
            image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        else:
            image = photo
        if image is None or image.ndim != 3 or min(image.shape[:2]) < 64:
            raise ValueError('Use a clear, well-lit face photo')
        scale = min(1, 960 / max(image.shape[:2]))
        if scale < 1:
            image = cv2.resize(image, (round(image.shape[1] * scale), round(image.shape[0] * scale)))
        with self.lock:
            self._load()
            self.detector.setInputSize((image.shape[1], image.shape[0]))
            _, faces = self.detector.detect(image)
            if faces is None or len(faces) != 1:
                raise ValueError('Exactly one clear face is required; do not include other people')
            face = faces[0]
            left, top, width, height = [int(value) for value in face[:4]]
            left, top = max(0, left), max(0, top)
            crop = image[top:min(image.shape[0], top + height), left:min(image.shape[1], left + width)]
            if min(width, height) < 64 or crop.size == 0:
                raise ValueError('Face is too small: at least 64 × 64 face pixels are required')
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            if cv2.Laplacian(gray, cv2.CV_64F).var() < 25 or not 20 <= float(gray.mean()) <= 235:
                raise ValueError('Face image is blurred or poorly lit; move closer and improve lighting')
            aligned = self.recognizer.alignCrop(image, face)
            feature = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)
            norm = float(np.linalg.norm(feature))
            if feature.size != 128 or not np.isfinite(feature).all() or norm < 1e-6:
                raise ValueError('No usable face template was produced')
            return feature / norm
