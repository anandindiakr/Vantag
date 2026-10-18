"""
8-state Kalman filter for bounding-box tracking (BoT-SORT motion model).

State: [cx, cy, w, h, vx, vy, vw, vh] — box center + size and their rates.
Measurement: [cx, cy, w, h].

This is the standard constant-velocity motion model used by SORT / DeepSORT /
BoT-SORT (Wojke et al. 2017; Aharon et al. 2022), adapted to track width
directly rather than aspect ratio: with independent x/y/w/h channels the
filter is conditionally linear and learns velocity correctly under the
predict-before-update ordering this tracker uses (the classic aspect-ratio
formulation freezes its velocity at zero in that ordering because the
size channel behaves non-linearly between two frames).

Implemented directly on numpy — which is already a hard dependency of this
agent — so no scipy / lap packages need to be installed on store laptops.

The filter replaces the ad-hoc 2-frame velocity estimate that ByteTracker used
before: predictions are smoothed (robust to single-frame detection jitter at
5 fps) and the uncertainty grows between updates, so a track that has gone
unmatched for a few frames still gets matched to the right re-appearing
detection instead of spawning a duplicate ID.
"""
import numpy as np


class KalmanBoxTracker:
    __slots__ = ("x", "P", "_F", "_H")

    _STD_WEIGHT_POSITION = 1.0 / 20.0
    _STD_WEIGHT_VELOCITY = 1.0 / 160.0

    def __init__(self, cx: float, cy: float, w: float, h: float):
        # State mean (8,) — starts at the first measurement, zero velocity.
        self.x = np.array([cx, cy, w, h, 0.0, 0.0, 0.0, 0.0], dtype=float)
        # State covariance (8, 8). Initial uncertainty follows the reference
        # SORT/BoT-SORT convention scaled to the observed box size.
        std = [
            2.0 * self._STD_WEIGHT_POSITION * h,
            2.0 * self._STD_WEIGHT_POSITION * h,
            2.0 * self._STD_WEIGHT_POSITION * h,
            2.0 * self._STD_WEIGHT_POSITION * h,
            10.0 * self._STD_WEIGHT_VELOCITY * h,
            10.0 * self._STD_WEIGHT_VELOCITY * h,
            10.0 * self._STD_WEIGHT_VELOCITY * h,
            10.0 * self._STD_WEIGHT_VELOCITY * h,
        ]
        self.P = np.diag(np.square(std))

        # Constant-velocity transition (8x8) and measurement (4x8) models.
        self._F = np.eye(8)
        for i in range(4):
            self._F[i, i + 4] = 1.0
        self._H = np.zeros((4, 8))
        for i in range(4):
            self._H[i, i] = 1.0

    def predict(self) -> None:
        h = self.x[3]
        std = [
            self._STD_WEIGHT_POSITION * h,
            self._STD_WEIGHT_POSITION * h,
            self._STD_WEIGHT_POSITION * h,
            self._STD_WEIGHT_POSITION * h,
            self._STD_WEIGHT_VELOCITY * h,
            self._STD_WEIGHT_VELOCITY * h,
            self._STD_WEIGHT_VELOCITY * h,
            self._STD_WEIGHT_VELOCITY * h,
        ]
        Q = np.diag(np.square(std))
        self.x = self._F @ self.x
        self.P = self._F @ self.P @ self._F.T + Q

    def update(self, cx: float, cy: float, w: float, h: float) -> None:
        z = np.array([cx, cy, w, h], dtype=float)
        std = [
            self._STD_WEIGHT_POSITION * h,
            self._STD_WEIGHT_POSITION * h,
            self._STD_WEIGHT_POSITION * h,
            self._STD_WEIGHT_POSITION * h,
        ]
        R = np.diag(np.square(std))
        y = z - self._H @ self.x
        S = self._H @ self.P @ self._H.T + R
        K = self.P @ self._H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(8) - K @ self._H) @ self.P

    def predicted_box(self):
        """Return the predicted (x, y, w, h) bounding box from the state."""
        cx, cy, w, h = self.x[0], self.x[1], self.x[2], self.x[3]
        w = max(1e-6, w)
        h = max(1e-6, h)
        return cx - w / 2.0, cy - h / 2.0, w, h
