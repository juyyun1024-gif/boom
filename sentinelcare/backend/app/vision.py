"""Vision module — OpenCV capture + MediaPipe PoseLandmarker (multi-person)."""

from __future__ import annotations

import base64
import os
import threading
import time
import cv2
import mediapipe as mp
import numpy as np
from typing import Optional, Tuple

from .models import LandmarkPoint, PoseData

# ---------------------------------------------------------------------------
# Skeleton topology (MediaPipe 33-landmark model)
# ---------------------------------------------------------------------------

CONNECTIONS = [
    # Torso
    (11, 12), (11, 23), (12, 24), (23, 24),
    # Left arm
    (11, 13), (13, 15),
    # Right arm
    (12, 14), (14, 16),
    # Left leg
    (23, 25), (25, 27),
    # Right leg
    (24, 26), (26, 28),
    # Left hand
    (15, 17), (15, 19), (15, 21),
    # Right hand
    (16, 18), (16, 20), (16, 22),
    # Left foot
    (27, 29), (27, 31),
    # Right foot
    (28, 30), (28, 32),
    # Face
    (0, 1), (0, 4),
    (1, 2), (2, 3), (3, 7),
    (4, 5), (5, 6), (6, 8),
    (9, 10),
]

# Joints to draw dots on (skip minor face/hand/foot points)
KEY_JOINTS = {0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28}

# Per-person colour palette (up to 6 people)
PERSON_COLORS = [
    ((0, 230, 180), (0, 180, 220)),   # Cyan-teal
    ((180, 120, 255), (140, 80, 230)), # Purple
    ((255, 180, 60), (230, 140, 30)),  # Gold
    ((100, 220, 100), (60, 180, 60)),  # Green
    ((255, 100, 130), (220, 60, 100)), # Pink
    ((100, 180, 255), (60, 140, 230)), # Blue
]


class PoseTracker:
    """Wraps MediaPipe PoseLandmarker (Tasks API) for multi-person tracking."""

    def __init__(
        self,
        model_path: str | None = None,
        num_poses: int = 6,
        min_detection_confidence: float = 0.3,
        min_tracking_confidence: float = 0.3,
    ) -> None:
        if model_path is None:
            # Look for model relative to this file or in backend root
            candidates = [
                os.path.join(os.path.dirname(__file__), "..", "pose_landmarker.task"),
                os.path.join(os.path.dirname(__file__), "pose_landmarker.task"),
                "pose_landmarker.task",
            ]
            for c in candidates:
                if os.path.exists(c):
                    model_path = c
                    break
            if model_path is None:
                raise FileNotFoundError(
                    "pose_landmarker.task not found. Download from: "
                    "https://storage.googleapis.com/mediapipe-models/"
                    "pose_landmarker/pose_landmarker_heavy/float16/latest/"
                    "pose_landmarker_heavy.task"
                )

        base_opts = mp.tasks.BaseOptions(model_asset_path=model_path)
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=base_opts,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=num_poses,
            min_pose_detection_confidence=min_detection_confidence,
            min_pose_presence_confidence=0.3,
            min_tracking_confidence=min_tracking_confidence,
            output_segmentation_masks=False,
        )
        self._detector = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        self._frame_ts = 0  # monotonic timestamp in ms

    def process_frame(
        self, frame: np.ndarray, draw_overlay: bool = True
    ) -> Tuple[np.ndarray, list[PoseData]]:
        """Process one BGR frame. Returns annotated frame + list of PoseData (one per person)."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        self._frame_ts += 33  # ~30 fps step
        result = self._detector.detect_for_video(mp_image, self._frame_ts)

        all_poses: list[PoseData] = []

        if result.pose_landmarks:
            for person_idx, person_lms in enumerate(result.pose_landmarks):
                landmarks = []
                for lm in person_lms:
                    landmarks.append(
                        LandmarkPoint(x=lm.x, y=lm.y, z=lm.z, visibility=lm.visibility)
                    )
                all_poses.append(PoseData(detected=True, landmarks=landmarks))

                if draw_overlay:
                    self._draw_skeleton(frame, landmarks, person_idx)

        return frame, all_poses

    def _draw_skeleton(
        self, frame: np.ndarray, landmarks: list[LandmarkPoint], person_idx: int
    ) -> None:
        """Draw a clean, minimal skeleton overlay for one person."""
        h, w = frame.shape[:2]
        colors = PERSON_COLORS[person_idx % len(PERSON_COLORS)]
        line_color = colors[0]   # BGR (already in right order for cv2)
        joint_color = colors[1]

        # Convert to pixel coordinates
        pts = []
        for lm in landmarks:
            px = int(lm.x * w)
            py = int(lm.y * h)
            pts.append((px, py, lm.visibility))

        # Draw connections — thin glow + crisp line
        for a, b in CONNECTIONS:
            if a >= len(pts) or b >= len(pts):
                continue
            vis = min(pts[a][2], pts[b][2])
            if vis < 0.3:
                continue

            p1 = (pts[a][0], pts[a][1])
            p2 = (pts[b][0], pts[b][1])

            # Outer glow (subtle)
            alpha = max(0.15, vis * 0.25)
            overlay = frame.copy()
            cv2.line(overlay, p1, p2, line_color, 4, cv2.LINE_AA)
            cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

            # Crisp line
            cv2.line(frame, p1, p2, line_color, 1, cv2.LINE_AA)

        # Draw key joints — small filled circles with subtle outer ring
        for idx in KEY_JOINTS:
            if idx >= len(pts):
                continue
            vis = pts[idx][2]
            if vis < 0.3:
                continue

            center = (pts[idx][0], pts[idx][1])

            # Outer glow ring
            overlay = frame.copy()
            cv2.circle(overlay, center, 6, joint_color, -1, cv2.LINE_AA)
            cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)

            # Inner dot
            cv2.circle(frame, center, 3, joint_color, -1, cv2.LINE_AA)

            # Bright center
            cv2.circle(frame, center, 1, (255, 255, 255), -1, cv2.LINE_AA)

    def close(self) -> None:
        self._detector.close()


class VideoCapture:
    """Manages OpenCV video capture from webcam or file."""

    def __init__(self, source: str = "0") -> None:
        self._source_str = source
        self._cap: Optional[cv2.VideoCapture] = None
        self._threaded = False
        self._reader_running = False
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_id = 0
        self._returned_frame_id = 0

    def open(self) -> bool:
        """Open the video source."""
        try:
            src = int(self._source_str)
        except ValueError:
            src = self._source_str

        self._cap = cv2.VideoCapture(src)

        if isinstance(src, int):
            self._threaded = True
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self._cap.set(cv2.CAP_PROP_FPS, 30)

        opened = self._cap.isOpened()
        if opened and self._threaded:
            self._reader_running = True
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                name="sentinelcare-camera-reader",
                daemon=True,
            )
            self._reader_thread.start()

        return opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a single frame."""
        if self._cap is None or not self._cap.isOpened():
            return False, None

        if self._threaded:
            deadline = time.time() + 0.05
            while time.time() < deadline:
                with self._lock:
                    has_new_frame = (
                        self._latest_frame is not None
                        and self._latest_frame_id != self._returned_frame_id
                    )
                    if has_new_frame:
                        self._returned_frame_id = self._latest_frame_id
                        return True, self._latest_frame.copy()
                time.sleep(0.002)
            return False, None

        ret, frame = self._cap.read()
        if not ret and isinstance(self._source_str, str) and not self._source_str.isdigit():
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
        return ret, frame

    def release(self) -> None:
        self._reader_running = False
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)
        self._reader_thread = None

        if self._cap is not None:
            self._cap.release()
        self._cap = None
        self._latest_frame = None

    def _reader_loop(self) -> None:
        """Continuously drain webcam frames and keep only the newest one."""
        while self._reader_running:
            if self._cap is None or not self._cap.isOpened():
                time.sleep(0.01)
                continue

            ret, frame = self._cap.read()
            if not ret or frame is None:
                time.sleep(0.005)
                continue

            with self._lock:
                self._latest_frame = frame
                self._latest_frame_id += 1

    @property
    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()


def frame_to_base64(frame: np.ndarray, quality: int = 70) -> str:
    """Encode a BGR frame as a base64 JPEG string."""
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    _, buffer = cv2.imencode(".jpg", frame, encode_params)
    return base64.b64encode(buffer).decode("utf-8")


def assess_frame_obstruction(frame: np.ndarray) -> tuple[bool, str, float]:
    """Detect lens-cover / unusable-camera frames before pose inference is trusted."""
    if frame is None or frame.size == 0:
        return True, "camera_obstructed", 0.0

    small = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    brightness = float(np.mean(gray)) / 255.0
    contrast = float(np.std(gray)) / 255.0
    color_std = float(np.mean(np.std(small.reshape(-1, 3), axis=0))) / 255.0
    saturation = float(np.mean(hsv[:, :, 1])) / 255.0
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edge_density = float(np.mean(cv2.Canny(gray, 40, 120) > 0))

    too_dark = brightness < 0.08
    too_bright = brightness > 0.97
    low_texture = laplacian_var < 18.0 and edge_density < 0.025
    uniform_frame = contrast < 0.075 and color_std < 0.075
    close_color_cover = saturation > 0.35 and color_std < 0.085 and edge_density < 0.035

    score = 0.0
    if too_dark or too_bright:
        score += 0.55
    if low_texture:
        score += 0.25
    if uniform_frame:
        score += 0.25
    if close_color_cover:
        score += 0.25

    obstructed = score >= 0.65 and (
        too_dark or too_bright or low_texture or close_color_cover
    )
    frame_quality = 1.0 - max(0.0, min(1.0, score))

    if obstructed:
        return True, "camera_obstructed", round(frame_quality, 4)
    return False, "ok", round(frame_quality, 4)
