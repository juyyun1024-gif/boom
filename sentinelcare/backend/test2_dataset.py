"""
SentinelCare Video Visualizer — Outputs annotated result MP4 files
===================================================================
Processes video files through the 5-feature fall detection pipeline
and writes annotated output videos with skeleton overlay, state info,
confidence bars, and feature readouts burned into each frame.

Usage:
    python test2_dataset.py datasets/sample/sample_1.mp4
    python test2_dataset.py datasets/sample/                   # all videos in folder
    python test2_dataset.py datasets/ --out results_video      # custom output folder

Output: result_<original_name>.mp4 saved to datasets/results_video/
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

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}

# BGR colors
COLOR_NORMAL = (0, 200, 0)
COLOR_SUSPICIOUS = (0, 220, 255)
COLOR_MONITORING = (0, 180, 255)
COLOR_CRITICAL = (0, 0, 255)
COLOR_RECOVERED = (0, 255, 120)
COLOR_WHITE = (255, 255, 255)
COLOR_DARK = (20, 20, 20)
COLOR_BAR_BG = (50, 50, 50)
COLOR_BAR_CONF = (0, 200, 255)
COLOR_BAR_POST = (255, 140, 0)

STATE_COLORS_BGR = {
    AgentStateName.NORMAL: COLOR_NORMAL,
    AgentStateName.SUSPICIOUS_EVENT: COLOR_SUSPICIOUS,
    AgentStateName.MONITORING_RECOVERY: COLOR_MONITORING,
    AgentStateName.RECOVERED: COLOR_RECOVERED,
    AgentStateName.CRITICAL_ALERT: COLOR_CRITICAL,
}


def find_videos(path: str) -> list[str]:
    """Find all video files in a path."""
    if os.path.isfile(path):
        if os.path.splitext(path)[1].lower() in VIDEO_EXTS:
            return [path]
        return []
    if not os.path.isdir(path):
        return []
    videos = []
    for entry in sorted(os.listdir(path)):
        full = os.path.join(path, entry)
        if os.path.isfile(full) and os.path.splitext(entry)[1].lower() in VIDEO_EXTS:
            videos.append(full)
        elif os.path.isdir(full):
            for sub in sorted(os.listdir(full)):
                sub_full = os.path.join(full, sub)
                if os.path.isfile(sub_full) and os.path.splitext(sub)[1].lower() in VIDEO_EXTS:
                    videos.append(sub_full)
    return videos


def draw_bar(frame, x, y, w, h, value, max_val, color, label, bg_color=COLOR_BAR_BG):
    """Draw a labeled horizontal bar."""
    cv2.rectangle(frame, (x, y), (x + w, y + h), bg_color, -1)
    fill_w = int(w * min(value / max_val, 1.0)) if max_val > 0 else 0
    if fill_w > 0:
        cv2.rectangle(frame, (x, y), (x + fill_w, y + h), color, -1)
    cv2.rectangle(frame, (x, y), (x + w, y + h), (80, 80, 80), 1)
    cv2.putText(frame, f"{label}: {value:.2f}", (x + 4, y + h - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLOR_WHITE, 1, cv2.LINE_AA)


def draw_overlay(frame, features, agent_state, frame_num, total_frames, fps, num_people):
    """Draw the full HUD overlay on a frame."""
    h, w = frame.shape[:2]
    state = agent_state.state
    state_color = STATE_COLORS_BGR.get(state, COLOR_NORMAL)

    # --- Top banner ---
    banner_h = 50
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), COLOR_DARK, -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    state_text = state.value.upper().replace("_", " ")
    cv2.putText(frame, state_text, (10, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, state_color, 2, cv2.LINE_AA)

    # Time / frame info on right
    current_time = frame_num / fps if fps > 0 else 0
    time_text = f"{current_time:.1f}s  [{frame_num}/{total_frames}]"
    (tw, _), _ = cv2.getTextSize(time_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.putText(frame, time_text, (w - tw - 10, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

    # --- State border glow ---
    if state == AgentStateName.CRITICAL_ALERT:
        # Pulsing red border for critical
        thickness = 4 + int(2 * abs((frame_num % 20) - 10) / 10)
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), COLOR_CRITICAL, thickness)
    elif state == AgentStateName.MONITORING_RECOVERY:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), COLOR_MONITORING, 2)
    elif state == AgentStateName.SUSPICIOUS_EVENT:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), COLOR_SUSPICIOUS, 2)

    # --- Left panel: feature readouts ---
    panel_y = banner_h + 10
    line_h = 22
    panel_x = 8

    texts = [
        (f"People: {num_people}", COLOR_NORMAL if num_people > 0 else COLOR_CRITICAL),
        (f"Posture Score: {features.posture_score:.2f}", COLOR_BAR_POST),
        (f"Body Angle: {features.body_axis_angle:.1f} deg", COLOR_WHITE),
        (f"CoG Height: {features.center_of_gravity_height:.3f}", COLOR_WHITE),
        (f"Aspect Ratio: {features.aspect_ratio:.2f}", COLOR_WHITE),
        (f"Motion: {features.sudden_motion_change:.4f}", COLOR_WHITE),
        (f"Stillness: {features.stillness_duration:.1f}s", COLOR_WHITE),
    ]

    # Dark background for text
    overlay2 = frame.copy()
    cv2.rectangle(overlay2, (0, banner_h), (250, banner_h + len(texts) * line_h + 15), COLOR_DARK, -1)
    cv2.addWeighted(overlay2, 0.6, frame, 0.4, 0, frame)

    for i, (text, color) in enumerate(texts):
        y = panel_y + i * line_h + 15
        cv2.putText(frame, text, (panel_x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    # --- Bottom bars: confidence + posture ---
    bar_y = h - 55
    bar_w = w - 20
    bar_h = 18

    # Dark background for bars
    overlay3 = frame.copy()
    cv2.rectangle(overlay3, (0, bar_y - 8), (w, h), COLOR_DARK, -1)
    cv2.addWeighted(overlay3, 0.6, frame, 0.4, 0, frame)

    draw_bar(frame, 10, bar_y, bar_w, bar_h, agent_state.confidence, 1.0,
             state_color, f"Confidence")
    draw_bar(frame, 10, bar_y + bar_h + 5, bar_w, bar_h, features.posture_score, 1.0,
             COLOR_BAR_POST, f"Posture")

    # --- Timer (if monitoring) ---
    if agent_state.timer_active:
        timer_text = f"Recovery Timer: {agent_state.timer_remaining:.1f}s / {agent_state.timer_total:.0f}s"
        (tw, th), _ = cv2.getTextSize(timer_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        tx = (w - tw) // 2
        ty = banner_h + 25
        cv2.rectangle(frame, (tx - 8, ty - th - 8), (tx + tw + 8, ty + 8), (0, 0, 180), -1)
        cv2.putText(frame, timer_text, (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_WHITE, 2, cv2.LINE_AA)

    return frame


def process_video(
    video_path: str,
    output_path: str,
    tracker: PoseTracker,
    recovery_window: float = 10.0,
    confidence_threshold: float = 0.55,
    sliding_window_size: int = 20,
    stillness_threshold: float = 0.005,
    ema_alpha: float = 0.3,
) -> dict:
    """Process a video and write annotated output."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"file": os.path.basename(video_path), "error": "Cannot open video"}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0

    filename = os.path.basename(video_path)
    print(f"\n  Processing: {filename} ({duration:.1f}s, {total_frames} frames, {fps:.0f}fps)")

    # Video writer
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

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
    max_confidence = 0.0
    max_posture = 0.0
    state_changes = 0
    prev_state = AgentStateName.NORMAL
    has_alert = False
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        frame_count += 1

        # Run pose detection with skeleton overlay
        annotated, all_poses = tracker.process_frame(frame.copy(), draw_overlay=True)

        any_detected = len(all_poses) > 0
        features = PoseFeatures()
        if any_detected:
            features = extractor.extract(all_poses[0])

        agent_state = agent.update(features, any_detected)
        max_confidence = max(max_confidence, agent_state.confidence)
        max_posture = max(max_posture, features.posture_score)

        if agent_state.state != prev_state:
            state_changes += 1
            if agent_state.state == AgentStateName.CRITICAL_ALERT:
                has_alert = True
            prev_state = agent_state.state

        # Draw HUD overlay
        annotated = draw_overlay(
            annotated, features, agent_state,
            frame_count, total_frames, fps, len(all_poses),
        )

        writer.write(annotated)

        # Progress
        if frame_count % 50 == 0 or frame_count == total_frames:
            pct = frame_count / total_frames * 100
            print(f"    {pct:5.1f}% ({frame_count}/{total_frames})", end="\r")

    cap.release()
    writer.release()

    elapsed = time.time() - start_time
    proc_fps = frame_count / elapsed if elapsed > 0 else 0

    icon = "🚨" if has_alert else "✅"
    print(f"    {icon} Done: {frame_count} frames in {elapsed:.1f}s ({proc_fps:.1f} fps)")
    print(f"       Max confidence: {max_confidence:.3f} | Max posture: {max_posture:.3f} | State changes: {state_changes}")
    print(f"       Output: {output_path}")

    return {
        "file": filename,
        "output": output_path,
        "frames": frame_count,
        "max_confidence": max_confidence,
        "max_posture": max_posture,
        "has_alert": has_alert,
        "state_changes": state_changes,
        "processing_fps": round(proc_fps, 1),
    }


def main():
    parser = argparse.ArgumentParser(
        description="SentinelCare Video Visualizer — writes annotated result MP4 files"
    )
    parser.add_argument("path", nargs="?", default="datasets/sample",
                        help="Video file or folder (default: datasets/sample)")
    parser.add_argument("--out", default=None,
                        help="Output directory (default: <input_dir>/results_video)")
    parser.add_argument("--recovery-window", type=float, default=10.0)
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--window-size", type=int, default=20)
    parser.add_argument("--stillness", type=float, default=0.005)
    parser.add_argument("--ema", type=float, default=0.3)
    args = parser.parse_args()

    videos = find_videos(args.path)
    if not videos:
        print(f"No video files found in: {args.path}")
        sys.exit(1)

    # Output directory
    if args.out:
        out_dir = args.out
    elif os.path.isfile(args.path):
        out_dir = os.path.join(os.path.dirname(args.path), "results_video")
    else:
        out_dir = os.path.join(args.path, "results_video")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\nSentinelCare Video Visualizer")
    print(f"Videos: {len(videos)}")
    print(f"Output: {out_dir}/")
    print(f"\nLoading MediaPipe PoseLandmarker...")

    tracker = PoseTracker()
    print(f"Model loaded.\n")

    results = []
    for video_path in videos:
        name = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(out_dir, f"result_{name}.mp4")

        r = process_video(
            video_path, output_path, tracker,
            recovery_window=args.recovery_window,
            confidence_threshold=args.threshold,
            sliding_window_size=args.window_size,
            stillness_threshold=args.stillness,
            ema_alpha=args.ema,
        )
        results.append(r)

    tracker.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"  VISUALIZATION COMPLETE")
    print(f"{'='*60}")
    for r in results:
        icon = "🚨" if r.get("has_alert") else "✅"
        print(f"  {icon} {r['file']:<30s} → {os.path.basename(r.get('output', ''))}")
    print(f"\n  Output folder: {out_dir}/")
    print(f"  Open the result_*.mp4 files in any video player to review.\n")


if __name__ == "__main__":
    main()
