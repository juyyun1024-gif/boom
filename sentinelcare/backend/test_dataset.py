"""
SentinelCare Dataset Tester
============================
Run fall detection on video files without needing the frontend/WebSocket.

Usage:
    python test_dataset.py                          # Test all videos in datasets/
    python test_dataset.py path/to/video.mp4        # Test a single video
    python test_dataset.py datasets/ --show         # Show video playback with overlay

Dataset sources (download manually from Kaggle/web):
    - https://www.kaggle.com/datasets/simuletic/cctv-incident-dataset-fall-and-lying-down-detection
    - https://fenix.ur.edu.pl/mkepski/ds/uf.html
    - https://www.kaggle.com/datasets/uttejkumarkandagatla/fall-detection-dat
    - https://www.kaggle.com/datasets/ivannikolov/thermal-mannequin-fall-image-dataset

Place .mp4 / .avi files in:
    sentinelcare/backend/datasets/
"""

import argparse
import os
import sys
import time
import cv2

# Add parent to path so we can import app modules
sys.path.insert(0, os.path.dirname(__file__))

from app.models import PoseFeatures, AgentStateName
from app.features import FeatureExtractor
from app.agent import FallGuardAgent
from app.vision import PoseTracker


# ANSI colors for terminal output
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


def find_videos(path: str) -> list[str]:
    """Find all video files in a directory."""
    video_exts = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}
    videos = []

    if os.path.isfile(path):
        return [path]

    for root, _, files in os.walk(path):
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in video_exts:
                videos.append(os.path.join(root, f))

    return videos


def test_video(
    video_path: str,
    tracker: PoseTracker,
    show: bool = False,
    recovery_window: float = 10.0,
    confidence_threshold: float = 0.55,
) -> dict:
    """Run fall detection on a single video file. Returns a result summary."""

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"file": video_path, "error": "Cannot open video"}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    agent = FallGuardAgent(
        recovery_window=recovery_window,
        confidence_threshold=confidence_threshold,
    )
    extractor = FeatureExtractor()

    frame_count = 0
    state_log = []
    events_detected = []
    max_confidence = 0.0
    prev_state = AgentStateName.NORMAL

    filename = os.path.basename(video_path)
    print(f"\n{'='*70}")
    print(f"{Colors.BOLD}{Colors.CYAN}Testing: {filename}{Colors.RESET}")
    print(f"  Duration: {duration:.1f}s | Frames: {total_frames} | FPS: {fps:.1f}")
    print(f"{'='*70}")

    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        current_time = frame_count / fps

        # Process frame
        annotated, all_poses = tracker.process_frame(frame, draw_overlay=show)

        # Extract features from first detected person
        any_detected = len(all_poses) > 0
        features = PoseFeatures()
        if any_detected:
            features = extractor.extract(all_poses[0])

        # Run agent
        agent_state = agent.update(features, any_detected)
        max_confidence = max(max_confidence, agent_state.confidence)

        # Log state changes
        if agent_state.state != prev_state:
            color = STATE_COLORS.get(agent_state.state, Colors.RESET)
            print(
                f"  [{current_time:6.1f}s] "
                f"{color}{agent_state.state.value:25s}{Colors.RESET} "
                f"confidence={agent_state.confidence:.3f}"
            )
            state_log.append({
                "time": round(current_time, 1),
                "state": agent_state.state.value,
                "confidence": agent_state.confidence,
            })

            if agent_state.state == AgentStateName.CRITICAL_ALERT:
                events_detected.append({
                    "type": "critical_alert",
                    "time": round(current_time, 1),
                    "confidence": agent_state.confidence,
                })
            elif agent_state.state == AgentStateName.RECOVERED:
                events_detected.append({
                    "type": "recovered",
                    "time": round(current_time, 1),
                })

            prev_state = agent_state.state

        # Show video if requested
        if show:
            # Draw status on frame
            state_text = agent_state.state.value.upper()
            color_bgr = (0, 255, 0)  # green
            if agent_state.state in (AgentStateName.SUSPICIOUS_EVENT, AgentStateName.MONITORING_RECOVERY):
                color_bgr = (0, 255, 255)  # yellow
            elif agent_state.state == AgentStateName.CRITICAL_ALERT:
                color_bgr = (0, 0, 255)  # red

            cv2.putText(annotated, f"State: {state_text}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_bgr, 2)
            cv2.putText(annotated, f"Confidence: {agent_state.confidence:.2f}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(annotated, f"Time: {current_time:.1f}s", (10, 85),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            if agent_state.timer_active:
                cv2.putText(annotated, f"Timer: {agent_state.timer_remaining:.1f}s",
                            (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            cv2.imshow(f"SentinelCare - {filename}", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord(" "):  # pause
                cv2.waitKey(0)

    cap.release()
    if show:
        cv2.destroyAllWindows()

    elapsed = time.time() - start_time
    processing_fps = frame_count / elapsed if elapsed > 0 else 0

    # Final summary
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

    print(f"  Max confidence: {max_confidence:.3f}")
    print(f"  Processing: {processing_fps:.1f} fps ({elapsed:.1f}s for {frame_count} frames)")

    return {
        "file": filename,
        "duration": round(duration, 1),
        "frames": frame_count,
        "max_confidence": round(max_confidence, 3),
        "final_state": final_state.value,
        "critical_alert": has_alert,
        "recovered": has_recovery,
        "state_changes": len(state_log),
        "events": events_detected,
        "processing_fps": round(processing_fps, 1),
    }


def print_summary(results: list[dict]) -> None:
    """Print a summary table of all test results."""
    print(f"\n\n{'='*70}")
    print(f"{Colors.BOLD}{Colors.CYAN}  DATASET TEST SUMMARY{Colors.RESET}")
    print(f"{'='*70}")
    print(f"  {'File':<35} {'Duration':>8} {'MaxConf':>8} {'Result':<20}")
    print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*20}")

    alerts = 0
    recoveries = 0
    normals = 0

    for r in results:
        if "error" in r:
            print(f"  {r['file']:<35} {'ERROR':>8} {'':>8} {r['error']}")
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
            f"  {r['file']:<35} {r['duration']:>7.1f}s "
            f"{r['max_confidence']:>7.3f} {result_str}"
        )

    total = len(results)
    print(f"\n  Total: {total} videos | "
          f"{Colors.RED}{alerts} alerts{Colors.RESET} | "
          f"{Colors.GREEN}{recoveries} recoveries{Colors.RESET} | "
          f"{Colors.GREEN}{normals} normal{Colors.RESET}")
    print()


def main():
    parser = argparse.ArgumentParser(description="SentinelCare Dataset Tester")
    parser.add_argument(
        "path",
        nargs="?",
        default="datasets",
        help="Path to video file or directory (default: datasets/)",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Show video playback with pose overlay",
    )
    parser.add_argument(
        "--recovery-window", type=float, default=10.0,
        help="Recovery window in seconds (default: 10)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.55,
        help="Fall confidence threshold (default: 0.55)",
    )
    args = parser.parse_args()

    # Find videos
    videos = find_videos(args.path)
    if not videos:
        print(f"\n{Colors.RED}No video files found in: {args.path}{Colors.RESET}")
        print(f"\nPlease download datasets and place .mp4 files in:")
        print(f"  sentinelcare/backend/datasets/\n")
        print(f"Recommended datasets:")
        print(f"  - https://www.kaggle.com/datasets/ivannikolov/thermal-mannequin-fall-image-dataset")
        print(f"  - https://www.kaggle.com/datasets/uttejkumarkandagatla/fall-detection-dat")
        print(f"  - https://www.kaggle.com/datasets/simuletic/cctv-incident-dataset-fall-and-lying-down-detection")
        sys.exit(1)

    print(f"\n{Colors.BOLD}SentinelCare Dataset Tester{Colors.RESET}")
    print(f"Found {len(videos)} video(s) to test")
    print(f"Recovery window: {args.recovery_window}s | Threshold: {args.threshold}")

    # Initialize pose tracker (shared across videos for efficiency)
    print(f"\nLoading MediaPipe PoseLandmarker model...")
    try:
        tracker = PoseTracker()
        print(f"{Colors.GREEN}Model loaded successfully{Colors.RESET}")
    except FileNotFoundError as e:
        print(f"\n{Colors.RED}ERROR: {e}{Colors.RESET}")
        print(f"\nDownload the model:")
        print(f"  Windows (PowerShell):")
        print(f'    Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task" -OutFile "pose_landmarker.task"')
        print(f"\n  Linux/Mac:")
        print(f'    wget -O pose_landmarker.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task')
        sys.exit(1)

    # Run tests
    results = []
    for video_path in videos:
        try:
            result = test_video(
                video_path,
                tracker,
                show=args.show,
                recovery_window=args.recovery_window,
                confidence_threshold=args.threshold,
            )
            results.append(result)
        except Exception as e:
            print(f"\n{Colors.RED}ERROR processing {video_path}: {e}{Colors.RESET}")
            results.append({"file": os.path.basename(video_path), "error": str(e)})

    tracker.close()

    # Print summary
    if len(results) > 1:
        print_summary(results)


if __name__ == "__main__":
    main()
