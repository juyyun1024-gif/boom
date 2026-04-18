"""
SentinelCare Dataset Tester — 5-Feature Fall Detection
========================================================
Run fall detection on video files OR JPEG frame sequence folders.

Usage:
    python test_dataset.py                              # Test all in datasets/
    python test_dataset.py path/to/video.mp4            # Test a single video
    python test_dataset.py path/to/frames_folder/       # Test a JPEG sequence folder
    python test_dataset.py datasets/ --show             # Show playback with overlay
    python test_dataset.py datasets/ --fps 25           # Set FPS for image sequences
    python test_dataset.py datasets/image.png           # Single image posture score

Detection method:
    Compares frame-to-frame pose differences using 5 core features:
    1. Body Axis Angle — shoulder→hip deviation from vertical
    2. Center of Gravity Height — how low the body is
    3. Aspect Ratio — body bounding box shape
    4. Sudden Motion Change — landmark displacement between frames
    5. Stillness Duration — how long the person has been motionless
"""

import argparse
import os
import sys
import time
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from app.models import PoseFeatures, AgentStateName
from app.features import FeatureExtractor
from app.agent import FallGuardAgent
from app.vision import PoseTracker


# ANSI colors
class Colors:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


STATE_COLORS = {
    AgentStateName.NORMAL: Colors.GREEN,
    AgentStateName.SUSPICIOUS_EVENT: Colors.YELLOW,
    AgentStateName.MONITORING_RECOVERY: Colors.YELLOW,
    AgentStateName.RECOVERED: Colors.GREEN,
    AgentStateName.CRITICAL_ALERT: Colors.RED,
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}


# ---------------------------------------------------------------------------
# Frame sources (unchanged from original)
# ---------------------------------------------------------------------------

class VideoSource:
    def __init__(self, path: str):
        self.path = path
        self.name = os.path.basename(path)
        self._cap = cv2.VideoCapture(path)

    @property
    def fps(self) -> float:
        return self._cap.get(cv2.CAP_PROP_FPS) or 30.0

    @property
    def total_frames(self) -> int:
        return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def is_opened(self) -> bool:
        return self._cap.isOpened()

    def read(self):
        return self._cap.read()

    def release(self):
        self._cap.release()


class ImageSequenceSource:
    def __init__(self, folder: str, fps: float = 25.0):
        self.path = folder
        self.name = os.path.basename(folder.rstrip("/\\"))
        self._fps = fps
        self._images = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS
        )
        self._index = 0

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def total_frames(self) -> int:
        return len(self._images)

    def is_opened(self) -> bool:
        return len(self._images) > 0

    def read(self):
        if self._index >= len(self._images):
            return False, None
        frame = cv2.imread(self._images[self._index])
        self._index += 1
        return (True, frame) if frame is not None else (False, None)

    def release(self):
        pass


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def is_image_sequence_folder(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    return any(os.path.splitext(f)[1].lower() in IMAGE_EXTS for f in os.listdir(path))


def is_single_image(path: str) -> bool:
    return os.path.isfile(path) and os.path.splitext(path)[1].lower() in IMAGE_EXTS


def find_sources(path: str, seq_fps: float = 25.0) -> list:
    sources = []
    if os.path.isfile(path):
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTS:
            return [VideoSource(path)]
        elif ext in IMAGE_EXTS:
            return []  # handled separately as single image
    if is_image_sequence_folder(path):
        return [ImageSequenceSource(path, fps=seq_fps)]
    if not os.path.isdir(path):
        return []
    for entry in sorted(os.listdir(path)):
        full = os.path.join(path, entry)
        if os.path.isfile(full) and os.path.splitext(entry)[1].lower() in VIDEO_EXTS:
            sources.append(VideoSource(full))
        elif os.path.isdir(full) and is_image_sequence_folder(full):
            sources.append(ImageSequenceSource(full, fps=seq_fps))
        elif os.path.isdir(full):
            for sub in sorted(os.listdir(full)):
                sub_full = os.path.join(full, sub)
                if os.path.isfile(sub_full) and os.path.splitext(sub)[1].lower() in VIDEO_EXTS:
                    sources.append(VideoSource(sub_full))
                elif os.path.isdir(sub_full) and is_image_sequence_folder(sub_full):
                    sources.append(ImageSequenceSource(sub_full, fps=seq_fps))
    return sources


# ---------------------------------------------------------------------------
# Single image evaluation
# ---------------------------------------------------------------------------

def test_single_image(
    img_path: str,
    tracker: PoseTracker,
    show: bool = False,
) -> dict:
    """Evaluate Posture Score on a single static image."""
    img = cv2.imread(img_path)
    if img is None:
        return {"file": os.path.basename(img_path), "error": "Cannot read image"}

    filename = os.path.basename(img_path)
    annotated, all_poses = tracker.process_frame(img.copy(), draw_overlay=True)

    if not all_poses:
        print(f"  ❓ {filename:<30s} | No pose detected")
        return {
            "file": filename, "people": 0, "posture_score": 0.0,
            "label": "NO POSE", "body_axis_angle": 0.0, "aspect_ratio": 0.0,
        }

    extractor = FeatureExtractor(window_size=5, fps=1.0)
    features = extractor.extract(all_poses[0])

    if features.posture_score >= 0.6:
        label = "LAYING / FALLEN"
        icon = "🚨"
        color = Colors.RED
    elif features.posture_score >= 0.35:
        label = "SUSPICIOUS"
        icon = "⚠️"
        color = Colors.YELLOW
    else:
        label = "NORMAL"
        icon = "✅"
        color = Colors.GREEN

    print(
        f"  {icon} {filename:<30s} | "
        f"Posture: {features.posture_score:.2f} | "
        f"Angle: {features.body_axis_angle:.1f}° | "
        f"AR: {features.aspect_ratio:.2f} | "
        f"{color}{label}{Colors.RESET}"
    )

    if show:
        h, w = annotated.shape[:2]
        cv2.putText(annotated, f"Posture: {features.posture_score:.2f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(annotated, f"Angle: {features.body_axis_angle:.1f} deg", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(annotated, f"AR: {features.aspect_ratio:.2f}", (10, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(annotated, label, (10, 115),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255) if "FALL" in label else (0, 255, 0), 2)
        cv2.imshow(f"SentinelCare - {filename}", annotated)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return {
        "file": filename,
        "people": len(all_poses),
        "posture_score": features.posture_score,
        "body_axis_angle": features.body_axis_angle,
        "aspect_ratio": features.aspect_ratio,
        "cog_height": features.center_of_gravity_height,
        "label": label,
    }


# ---------------------------------------------------------------------------
# Video / sequence test runner
# ---------------------------------------------------------------------------

def test_source(
    source,
    tracker: PoseTracker,
    show: bool = False,
    recovery_window: float = 10.0,
    confidence_threshold: float = 0.55,
    sliding_window_size: int = 20,
    stillness_threshold: float = 0.005,
    ema_alpha: float = 0.3,
) -> dict:
    """Run 5-feature fall detection on a video or image sequence."""

    if not source.is_opened():
        return {"file": source.name, "error": "Cannot open source"}

    fps = source.fps
    total_frames = source.total_frames
    duration = total_frames / fps if fps > 0 else 0
    source_type = "images" if isinstance(source, ImageSequenceSource) else "video"

    agent = FallGuardAgent(
        recovery_window=recovery_window,
        confidence_threshold=confidence_threshold,
        ema_alpha=ema_alpha,
    )
    extractor = FeatureExtractor(
        window_size=sliding_window_size,
        fps=fps,
        stillness_threshold=stillness_threshold,
    )

    frame_count = 0
    state_log = []
    events_detected = []
    max_confidence = 0.0
    max_posture = 0.0
    prev_state = AgentStateName.NORMAL

    print(f"\n{'='*70}")
    print(f"{Colors.BOLD}{Colors.CYAN}Testing: {source.name}{Colors.RESET} ({source_type})")
    print(f"  Duration: {duration:.1f}s | Frames: {total_frames} | FPS: {fps:.1f}")
    print(f"  Window: {sliding_window_size} frames | Stillness: {stillness_threshold} | EMA α: {ema_alpha}")
    print(f"{'='*70}")

    start_time = time.time()

    while True:
        ret, frame = source.read()
        if not ret or frame is None:
            break

        frame_count += 1
        current_time = frame_count / fps

        annotated, all_poses = tracker.process_frame(frame, draw_overlay=show)

        any_detected = len(all_poses) > 0
        features = PoseFeatures()
        if any_detected:
            features = extractor.extract(all_poses[0])

        agent_state = agent.update(features, any_detected)
        max_confidence = max(max_confidence, agent_state.confidence)
        max_posture = max(max_posture, features.posture_score)

        # Log state changes
        if agent_state.state != prev_state:
            color = STATE_COLORS.get(agent_state.state, Colors.RESET)
            print(
                f"  [{current_time:6.1f}s] "
                f"{color}{agent_state.state.value:25s}{Colors.RESET} "
                f"conf={agent_state.confidence:.3f} "
                f"posture={features.posture_score:.2f} "
                f"angle={features.body_axis_angle:.1f}°"
            )
            state_log.append({
                "time": round(current_time, 1),
                "state": agent_state.state.value,
                "confidence": agent_state.confidence,
                "posture_score": features.posture_score,
            })

            if agent_state.state == AgentStateName.CRITICAL_ALERT:
                events_detected.append({"type": "critical_alert", "time": round(current_time, 1), "confidence": agent_state.confidence})
            elif agent_state.state == AgentStateName.RECOVERED:
                events_detected.append({"type": "recovered", "time": round(current_time, 1)})

            prev_state = agent_state.state

        # Show frame
        if show:
            state_text = agent_state.state.value.upper()
            color_bgr = (0, 255, 0)
            if agent_state.state in (AgentStateName.SUSPICIOUS_EVENT, AgentStateName.MONITORING_RECOVERY):
                color_bgr = (0, 255, 255)
            elif agent_state.state == AgentStateName.CRITICAL_ALERT:
                color_bgr = (0, 0, 255)

            h, w = annotated.shape[:2]
            if w > 1280:
                scale = 1280 / w
                annotated = cv2.resize(annotated, (int(w * scale), int(h * scale)))
            elif w < 320:
                scale = 640 / w
                annotated = cv2.resize(annotated, (int(w * scale), int(h * scale)))

            cv2.putText(annotated, f"State: {state_text}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_bgr, 2)
            cv2.putText(annotated, f"Confidence: {agent_state.confidence:.2f}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(annotated, f"Posture: {features.posture_score:.2f} | Angle: {features.body_axis_angle:.1f}", (10, 85),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
            cv2.putText(annotated, f"AR: {features.aspect_ratio:.2f} | Motion: {features.sudden_motion_change:.4f}", (10, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            if any_detected:
                cv2.putText(annotated, f"Pose: DETECTED ({len(all_poses)})", (10, 135),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
            else:
                cv2.putText(annotated, "Pose: NOT DETECTED", (10, 135),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

            if agent_state.timer_active:
                cv2.putText(annotated, f"Timer: {agent_state.timer_remaining:.1f}s", (10, 160),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            cv2.imshow(f"SentinelCare - {source.name}", annotated)
            wait_ms = max(1, int(1000 / fps)) if isinstance(source, ImageSequenceSource) else 1
            key = cv2.waitKey(wait_ms) & 0xFF
            if key == ord("q"):
                break
            elif key == ord(" "):
                cv2.waitKey(0)

    source.release()
    if show:
        cv2.destroyAllWindows()

    elapsed = time.time() - start_time
    processing_fps = frame_count / elapsed if elapsed > 0 else 0

    final_state = prev_state
    has_alert = any(e["type"] == "critical_alert" for e in events_detected)
    has_recovery = any(e["type"] == "recovered" for e in events_detected)

    result_icon = "✅" if not has_alert else "🚨"
    if has_recovery:
        result_icon = "🔄"

    print(f"\n  {Colors.BOLD}Result:{Colors.RESET} {result_icon} ", end="")
    if has_alert:
        print(f"{Colors.RED}CRITICAL ALERT TRIGGERED{Colors.RESET}")
    elif has_recovery:
        print(f"{Colors.GREEN}FALL DETECTED → RECOVERED{Colors.RESET}")
    elif any(s["state"] == "suspicious_event" for s in state_log):
        print(f"{Colors.YELLOW}SUSPICIOUS ACTIVITY (no escalation){Colors.RESET}")
    else:
        print(f"{Colors.GREEN}NORMAL (no fall detected){Colors.RESET}")

    print(f"  Max confidence: {max_confidence:.3f} | Max posture: {max_posture:.3f}")
    print(f"  Processing: {processing_fps:.1f} fps ({elapsed:.1f}s for {frame_count} frames)")

    return {
        "file": source.name,
        "type": source_type,
        "duration": round(duration, 1),
        "frames": frame_count,
        "max_confidence": round(max_confidence, 3),
        "max_posture": round(max_posture, 3),
        "final_state": final_state.value,
        "critical_alert": has_alert,
        "recovered": has_recovery,
        "state_changes": len(state_log),
        "events": events_detected,
        "processing_fps": round(processing_fps, 1),
    }


def print_summary(results: list[dict]) -> None:
    print(f"\n\n{'='*70}")
    print(f"{Colors.BOLD}{Colors.CYAN}  DATASET TEST SUMMARY{Colors.RESET}")
    print(f"{'='*70}")
    print(f"  {'Source':<30} {'Type':<8} {'Dur':>6} {'Conf':>6} {'Post':>6} {'Result':<20}")
    print(f"  {'-'*30} {'-'*8} {'-'*6} {'-'*6} {'-'*6} {'-'*20}")

    alerts = recoveries = normals = 0

    for r in results:
        if "error" in r:
            print(f"  {r['file']:<30} {'':>8} {'ERR':>6} {'':>6} {'':>6} {r['error']}")
            continue

        if r["critical_alert"]:
            result_str = f"{Colors.RED}🚨 ALERT{Colors.RESET}"
            alerts += 1
        elif r["recovered"]:
            result_str = f"{Colors.GREEN}🔄 RECOVERED{Colors.RESET}"
            recoveries += 1
        else:
            result_str = f"{Colors.GREEN}✅ NORMAL{Colors.RESET}"
            normals += 1

        print(
            f"  {r['file']:<30} {r['type']:<8} "
            f"{r['duration']:>5.1f}s {r['max_confidence']:>5.3f} "
            f"{r.get('max_posture', 0):>5.3f} {result_str}"
        )

    total = len(results)
    print(f"\n  Total: {total} | "
          f"{Colors.RED}{alerts} alerts{Colors.RESET} | "
          f"{Colors.GREEN}{recoveries} recoveries{Colors.RESET} | "
          f"{Colors.GREEN}{normals} normal{Colors.RESET}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="SentinelCare 5-Feature Fall Detection Tester"
    )
    parser.add_argument("path", nargs="?", default="datasets",
                        help="Video file, image, folder, or directory (default: datasets/)")
    parser.add_argument("--show", action="store_true", help="Show playback with overlay")
    parser.add_argument("--fps", type=float, default=25.0, help="FPS for image sequences")
    parser.add_argument("--recovery-window", type=float, default=5.0, help="Recovery window seconds")
    parser.add_argument("--threshold", type=float, default=0.45, help="Fall confidence threshold")
    parser.add_argument("--window-size", type=int, default=20, help="Sliding window size (frames)")
    parser.add_argument("--stillness", type=float, default=0.005, help="Stillness threshold")
    parser.add_argument("--ema", type=float, default=0.3, help="EMA smoothing alpha")
    args = parser.parse_args()

    # --- Single image mode ---
    if is_single_image(args.path):
        print(f"\n{Colors.BOLD}SentinelCare — Single Image Posture Evaluation{Colors.RESET}")
        print(f"Loading model...")
        tracker = PoseTracker()
        print(f"{Colors.GREEN}Model loaded{Colors.RESET}\n")
        test_single_image(args.path, tracker, show=args.show)
        tracker.close()
        return

    # --- Video / sequence mode ---
    sources = find_sources(args.path, seq_fps=args.fps)

    # Also check for loose images in the directory for batch posture scoring
    loose_images = []
    if os.path.isdir(args.path):
        for f in sorted(os.listdir(args.path)):
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                loose_images.append(os.path.join(args.path, f))

    if not sources and not loose_images:
        print(f"\n{Colors.RED}No videos, sequences, or images found in: {args.path}{Colors.RESET}")
        sys.exit(1)

    print(f"\n{Colors.BOLD}SentinelCare 5-Feature Fall Detection Tester{Colors.RESET}")
    print(f"Found: {len(sources)} video/sequence(s), {len(loose_images)} loose image(s)")
    print(f"Config: window={args.window_size} | threshold={args.threshold} | "
          f"stillness={args.stillness} | EMA α={args.ema}")

    print(f"\nLoading MediaPipe PoseLandmarker model...")
    try:
        tracker = PoseTracker()
        print(f"{Colors.GREEN}Model loaded successfully{Colors.RESET}")
    except FileNotFoundError as e:
        print(f"\n{Colors.RED}ERROR: {e}{Colors.RESET}")
        sys.exit(1)

    # Process loose images first (posture score only)
    if loose_images:
        print(f"\n{Colors.BOLD}--- Static Image Posture Scores ---{Colors.RESET}")
        img_results = []
        for img_path in loose_images:
            r = test_single_image(img_path, tracker, show=False)
            img_results.append(r)

        detected = sum(1 for r in img_results if r.get("people", 0) > 0)
        fallen = sum(1 for r in img_results if r.get("label") == "LAYING / FALLEN")
        print(f"\n  Images: {len(img_results)} | Detected: {detected} | Fallen: {fallen}")

    # Process videos / sequences
    if sources:
        print(f"\n{Colors.BOLD}--- Video Fall Detection ---{Colors.RESET}")
        results = []
        for source in sources:
            try:
                result = test_source(
                    source, tracker,
                    show=args.show,
                    recovery_window=args.recovery_window,
                    confidence_threshold=args.threshold,
                    sliding_window_size=args.window_size,
                    stillness_threshold=args.stillness,
                    ema_alpha=args.ema,
                )
                results.append(result)
            except Exception as e:
                print(f"\n{Colors.RED}ERROR processing {source.name}: {e}{Colors.RESET}")
                results.append({"file": source.name, "error": str(e)})

        if len(results) > 1:
            print_summary(results)

    tracker.close()


if __name__ == "__main__":
    main()
