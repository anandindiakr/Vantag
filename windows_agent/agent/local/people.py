from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .faces import LocalFaceEngine
from .vault import protect, unprotect

DEFAULTS = {'capture_enabled': False, 'recognition_enabled': False, 'retention_days': 7}


def appearance(crop) -> list[float]:
    import cv2
    image = cv2.resize(crop, (48, 96))
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    descriptors = []
    for band in np.array_split(hsv, 3):
        histogram = cv2.calcHist([band], [0, 1], None, [12, 4], [0, 180, 0, 256]).reshape(-1)
        descriptors.extend(np.sqrt(histogram / max(1, histogram.sum())).tolist())
    values = np.asarray(descriptors, np.float32)
    return (values / max(1e-9, float(np.linalg.norm(values)))).tolist()


class LocalPeopleTools:
    def __init__(self, store, licence, model_dir, face_engine=None):
        self.store = store
        self.licence = licence
        self.faces = face_engine or LocalFaceEngine(model_dir)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='local-people')
        self._job_lock = threading.Lock()
        self._pending = False
        self._last_samples = {}
        self._staff_hits = {}
        self._closed = False
        self.status = {'error': '', 'processing_ms': None, 'queue_skipped': 0, 'last_processed_at': None, 'method': 'Body-colour appearance ranking, not identity proof', 'field_accuracy_verified': False}

    def permitted(self):
        entitlement = self.licence.status()
        return entitlement.can_process and 'people_count' in entitlement.claims.get('features', [])

    def settings(self):
        return {**DEFAULTS, **self.store.get('people_tools', {})}

    def configure(self, settings: dict):
        capture = bool(settings.get('capture_enabled'))
        recognition = bool(settings.get('recognition_enabled'))
        if capture or recognition:
            if not self.permitted():
                raise ValueError('A valid people-count entitlement is required for new processing')
            if not settings.get('authorised'):
                raise ValueError('Confirm workplace authorisation and privacy notices before enabling people tools')
        if recognition and not capture:
            raise ValueError('Enable local observations before staff recognition')
        days = int(settings.get('retention_days', 7))
        if not 1 <= days <= 30:
            raise ValueError('Choose 1 to 30 days of people-observation retention')
        if recognition:
            self.faces.initialize() if hasattr(self.faces, 'initialize') else None
        with self.store.lock:
            self.store.set('people_tools', {'capture_enabled': capture, 'recognition_enabled': recognition, 'retention_days': days})
            self.store.audit(f'People tools settings: capture={capture}, recognition={recognition}, retention_days={days}; owner confirmed authorisation')
        return self.settings()

    def staff(self):
        with self.store.connect() as connection:
            return [dict(row) for row in connection.execute('SELECT id,staff_code,name,consent_note,consent_at FROM staff_profiles ORDER BY name COLLATE NOCASE')]

    def enrol(self, data: dict):
        if not self.permitted():
            raise ValueError('A valid people-count entitlement is required for enrolment')
        if data.get('consent') is not True or len(data.get('consent_note', '').strip()) < 10:
            raise ValueError('Record explicit staff consent and how it was obtained')
        photos = data.get('photos', [])
        if not 3 <= len(photos) <= 5 or len(set(photos)) != len(photos):
            raise ValueError('Use three to five different clear photos of the same consenting staff member')
        vectors = [self.faces.template(photo) for photo in photos]
        if any(float(np.dot(vectors[0], vector)) < 0.4 for vector in vectors[1:]):
            raise ValueError('Photos do not consistently match one face. Retake clear photos of the same staff member')
        identifier = str(uuid.uuid4())
        now = time.time()
        with self.store.lock, self.store.connect() as connection:
            if connection.execute('SELECT COUNT(*) FROM staff_profiles').fetchone()[0] >= 500:
                raise ValueError('This local staff directory supports up to 500 profiles')
            try:
                connection.execute('INSERT INTO staff_profiles VALUES (?, ?, ?, ?, ?, ?)', (identifier, data['staff_code'].strip(), data['name'].strip(), data['consent_note'].strip(), now, protect(json.dumps([vector.tolist() for vector in vectors]))))
            except sqlite3.IntegrityError as exc:
                raise ValueError('That staff code is already enrolled') from exc
            connection.execute('INSERT INTO audit(created_at,action) VALUES (?,?)', (now, f'Staff consent enrolment: {identifier}; local owner'))
        return next(profile for profile in self.staff() if profile['id'] == identifier)

    def delete_staff(self, staff_id):
        with self.store.lock, self.store.connect() as connection:
            connection.execute('PRAGMA secure_delete=ON')
            if not connection.execute('SELECT 1 FROM staff_profiles WHERE id=?', (staff_id,)).fetchone():
                raise LookupError('Staff profile not found')
            connection.execute('UPDATE person_observations SET staff_id=NULL,staff_score=NULL WHERE staff_id=?', (staff_id,))
            connection.execute('DELETE FROM staff_profiles WHERE id=?', (staff_id,))
            connection.execute('INSERT INTO audit(created_at,action) VALUES (?,?)', (time.time(), f'Staff consent revoked and profile deleted: {staff_id}; existing external backups must be handled separately'))
        self._staff_hits.clear()

    def match_face(self, photo):
        try:
            vector = self.faces.template(photo)
        except ValueError:
            return None
        matches = []
        with self.store.connect() as connection:
            for row in connection.execute('SELECT id,templates FROM staff_profiles'):
                templates = np.asarray(json.loads(unprotect(row['templates'])), np.float32)
                matches.append((float(np.max(templates @ vector)), row['id']))
        matches.sort(reverse=True)
        if not matches or matches[0][0] < 0.55 or len(matches) > 1 and matches[0][0] - matches[1][0] < 0.08:
            return None
        return {'staff_id': matches[0][1], 'score': round(matches[0][0], 4)}

    def submit(self, camera_id, run_id, boxes, frame, allowed):
        now = time.time()
        if not boxes or not self.settings()['capture_enabled'] or not self.permitted() or not allowed() or self._closed:
            return
        with self._job_lock:
            if now - self._last_samples.get(camera_id, 0) < 2:
                return
            if self._pending:
                self.status['queue_skipped'] += 1
                return
            self._last_samples[camera_id] = now
            self._pending = True
        self._executor.submit(self._process, camera_id, run_id, list(boxes[:8]), frame.copy(), allowed)

    def _process(self, camera_id, run_id, boxes, frame, allowed):
        started = time.monotonic()
        try:
            if allowed():
                self.observe(camera_id, run_id, boxes, frame, allowed=allowed)
            self.status.update(error='', last_processed_at=time.time())
        except Exception as exc:
            self.status['error'] = f'People observation processing failed: {type(exc).__name__}. Check models, image quality and storage.'
        finally:
            self.status['processing_ms'] = round((time.monotonic() - started) * 1000, 1)
            with self._job_lock:
                self._pending = False

    def observe(self, camera_id, run_id, boxes, frame, *, now=None, allowed=lambda: True):
        import cv2
        from .storage import require_capacity
        now = time.time() if now is None else now
        if not self.settings()['capture_enabled'] or not self.permitted() or not allowed():
            return
        require_capacity(self.store)
        self.prune(now)
        height, width = frame.shape[:2]
        for box in boxes[:8]:
            if getattr(box, 'track_id', None) is None:
                continue
            left, top = max(0, int(box.x * width)), max(0, int(box.y * height))
            right, bottom = min(width, int((box.x + box.w) * width)), min(height, int((box.y + box.h) * height))
            crop = frame[top:bottom, left:right]
            if crop.size == 0 or min(crop.shape[:2]) < 24:
                continue
            identifier = hashlib.sha256(f'{camera_id}:{run_id}:{box.track_id}'.encode()).hexdigest()[:32]
            descriptor = protect(json.dumps(appearance(crop)))
            scale = min(1, 240 / max(crop.shape[:2]))
            thumbnail = cv2.resize(crop, (round(crop.shape[1] * scale), round(crop.shape[0] * scale)))
            ok, encoded = cv2.imencode('.jpg', thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ok:
                raise ValueError('Observation image encoding failed')
            match = self.match_face(crop) if self.settings()['recognition_enabled'] else None
            previous = self._staff_hits.get(identifier)
            if match:
                hits = previous[1] + 1 if previous and previous[0] == match['staff_id'] else 1
                self._staff_hits[identifier] = (match['staff_id'], hits)
                if hits < 2:
                    match = None
            else:
                self._staff_hits.pop(identifier, None)
            if len(self._staff_hits) > 1000:
                self._staff_hits.clear()
            with self.store.lock, self.store.connect() as connection:
                if not self.settings()['capture_enabled'] or not self.permitted() or not allowed():
                    return
                if match and (not self.settings()['recognition_enabled'] or not connection.execute('SELECT 1 FROM staff_profiles WHERE id=?', (match['staff_id'],)).fetchone()):
                    match = None
                connection.execute('INSERT INTO person_observations VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,descriptor=excluded.descriptor,thumbnail=excluded.thumbnail,staff_id=excluded.staff_id,staff_score=excluded.staff_score', (identifier, camera_id, run_id, int(box.track_id), now, now, descriptor, protect(base64.b64encode(encoded).decode()), match['staff_id'] if match else None, match['score'] if match else None))

    def prune(self, now=None):
        cutoff = (time.time() if now is None else now) - self.settings()['retention_days'] * 86400
        with self.store.lock, self.store.connect() as connection:
            connection.execute('PRAGMA secure_delete=ON')
            connection.execute('DELETE FROM person_observations WHERE last_seen<?', (cutoff,))
            connection.execute('DELETE FROM person_links WHERE seed_id NOT IN (SELECT id FROM person_observations) OR target_id NOT IN (SELECT id FROM person_observations)')

    @staticmethod
    def public(row):
        return {key: row[key] for key in ('id', 'camera_id', 'first_seen', 'last_seen', 'staff_id', 'staff_score', 'staff_name') if key in row.keys()}

    def observations(self, *, camera_id='', page=1, page_size=30, now=None):
        self.prune(now)
        where, values = (' WHERE p.camera_id=?', [camera_id]) if camera_id else ('', [])
        with self.store.connect() as connection:
            total = connection.execute('SELECT COUNT(*) FROM person_observations p' + where, values).fetchone()[0]
            rows = connection.execute('SELECT p.*,s.name AS staff_name FROM person_observations p LEFT JOIN staff_profiles s ON s.id=p.staff_id' + where + ' ORDER BY p.last_seen DESC,p.id DESC LIMIT ? OFFSET ?', (*values, page_size, (page - 1) * page_size)).fetchall()
        return {'items': [self.public(row) for row in rows], 'total': total, 'page': page, 'page_size': page_size}

    def thumbnail(self, identifier):
        with self.store.connect() as connection:
            row = connection.execute('SELECT thumbnail FROM person_observations WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise LookupError('Observation not found or retention period ended')
        return base64.b64decode(unprotect(row['thumbnail']), validate=True)

    def candidates(self, seed_id, *, minutes=30, now=None):
        self.prune(now)
        with self.store.connect() as connection:
            seed = connection.execute('SELECT * FROM person_observations WHERE id=?', (seed_id,)).fetchone()
            if not seed:
                raise LookupError('Selected observation not found or retention period ended')
            rows = connection.execute('SELECT p.*,l.state AS review_state FROM person_observations p LEFT JOIN person_links l ON l.seed_id=? AND l.target_id=p.id WHERE p.camera_id<>? AND p.last_seen>=? AND p.first_seen<=? ORDER BY p.last_seen DESC LIMIT 2001', (seed_id, seed['camera_id'], seed['first_seen'] - minutes * 60, seed['last_seen'] + minutes * 60)).fetchall()
        descriptor = np.asarray(json.loads(unprotect(seed['descriptor'])), np.float32)
        ranked = []
        for row in rows[:2000]:
            score = float(np.dot(descriptor, np.asarray(json.loads(unprotect(row['descriptor'])), np.float32)))
            ranked.append({**self.public(row), 'appearance_score': round(score, 4), 'state': 'possible_appearance_match', 'review_state': row['review_state'] or 'unreviewed'})
        ranked.sort(key=lambda row: (-row['appearance_score'], row['id']))
        self.store.audit(f'Owner searched cross-camera appearances for {seed_id}; window={minutes} minutes')
        return {'items': ranked[:30], 'searched': min(len(rows), 2000), 'truncated': len(rows) > 2000, 'method': self.status['method'], 'identity_confirmed': False}

    def review_link(self, seed_id, target_id, state):
        if state not in ('confirmed', 'rejected') or seed_id == target_id:
            raise ValueError('Choose an operator confirmation or rejection for a different observation')
        with self.store.lock, self.store.connect() as connection:
            if connection.execute('SELECT COUNT(*) FROM person_observations WHERE id IN (?,?)', (seed_id, target_id)).fetchone()[0] != 2:
                raise LookupError('Observation not found or retention period ended')
            connection.execute('INSERT INTO person_links VALUES (?,?,?,?) ON CONFLICT(seed_id,target_id) DO UPDATE SET state=excluded.state,reviewed_at=excluded.reviewed_at', (seed_id, target_id, state, time.time()))
            connection.execute('INSERT INTO audit(created_at,action) VALUES (?,?)', (time.time(), f'Cross-camera link {seed_id} -> {target_id}: operator {state}'))

    def timeline(self, seed_id):
        with self.store.connect() as connection:
            rows = connection.execute("SELECT p.*,s.name AS staff_name FROM person_observations p LEFT JOIN staff_profiles s ON s.id=p.staff_id WHERE p.id=? OR p.id IN (SELECT target_id FROM person_links WHERE seed_id=? AND state='confirmed') ORDER BY p.first_seen,p.id", (seed_id, seed_id)).fetchall()
        return {'items': [self.public(row) for row in rows], 'continuity_verified': False, 'note': 'Operator-linked observations only. Camera gaps and similar clothing prevent guaranteed identity or uninterrupted tracking.'}

    def clear_observations(self):
        with self.store.lock, self.store.connect() as connection:
            connection.execute('PRAGMA secure_delete=ON')
            connection.execute('DELETE FROM person_links')
            connection.execute('DELETE FROM person_observations')
            connection.execute('INSERT INTO audit(created_at,action) VALUES (?,?)', (time.time(), 'Owner explicitly cleared people observations and links; incident archive retained'))
        self._staff_hits.clear()

    def close(self):
        self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=True)
