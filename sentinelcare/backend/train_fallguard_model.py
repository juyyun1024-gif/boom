"""Train the FallGuard sequence model.

This script trains the sklearn model consumed by app.ai_fall_model.AIFallRiskModel.
It can use real RGB fall datasets when present, and it always adds hard negative
examples for slow lie-down, sleeping, and normal activity.

Examples:
    python train_fallguard_model.py
    python train_fallguard_model.py --data-dir datasets/urfall
"""

from __future__ import annotations

import argparse
import pickle
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

FEATURE_NAMES = [
    "body_centroid_y",
    "torso_angle",
    "head_height",
    "hip_height",
    "velocity",
    "motion_energy",
    "stillness_score",
    "ground_proximity",
]

VIDEO_EXTENSIONS = {".avi", ".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def feature_vector(f) -> list[float]:
    return [
        float(f.body_centroid_y),
        float(f.torso_angle),
        float(f.head_height),
        float(f.hip_height),
        float(f.velocity),
        float(f.motion_energy),
        float(f.stillness_score),
        float(f.ground_proximity),
    ]


def clip_sequence(sequence: np.ndarray) -> np.ndarray:
    sequence[:, 0] = np.clip(sequence[:, 0], 0.05, 0.95)
    sequence[:, 1] = np.clip(sequence[:, 1], 0.0, 90.0)
    sequence[:, 2] = np.clip(sequence[:, 2], 0.02, 0.95)
    sequence[:, 3] = np.clip(sequence[:, 3], 0.05, 0.95)
    sequence[:, 4] = np.clip(sequence[:, 4], -0.12, 0.14)
    sequence[:, 5] = np.clip(sequence[:, 5], 0.0, 1.2)
    sequence[:, 6] = np.clip(sequence[:, 6], 0.0, 1.0)
    sequence[:, 7] = np.clip(sequence[:, 7], 0.0, 1.0)
    return sequence


def noisy(value: float, sigma: float, rng: np.random.Generator) -> float:
    return float(value + rng.normal(0.0, sigma))


def make_fall_sequence(window_size: int, rng: np.random.Generator) -> np.ndarray:
    sequence = []
    stand_frames = int(rng.integers(7, 12))
    fall_frames = int(rng.integers(4, 8))

    for _ in range(stand_frames):
        sequence.append([
            noisy(0.32, 0.025, rng),
            noisy(6.0, 4.0, rng),
            noisy(0.20, 0.02, rng),
            noisy(0.38, 0.025, rng),
            noisy(0.0, 0.006, rng),
            noisy(0.03, 0.015, rng),
            noisy(0.78, 0.08, rng),
            noisy(0.18, 0.05, rng),
        ])

    for t in range(fall_frames):
        progress = (t + 1) / fall_frames
        sequence.append([
            noisy(0.32 + progress * 0.34, 0.025, rng),
            noisy(8.0 + progress * 62.0, 7.0, rng),
            noisy(0.20 + progress * 0.36, 0.025, rng),
            noisy(0.38 + progress * 0.28, 0.025, rng),
            noisy(0.035 + progress * 0.06, 0.012, rng),
            noisy(0.22 + progress * 0.30, 0.06, rng),
            noisy(0.40 - progress * 0.25, 0.08, rng),
            noisy(0.18 + progress * 0.58, 0.06, rng),
        ])

    while len(sequence) < window_size:
        sequence.append([
            noisy(0.68, 0.025, rng),
            noisy(72.0, 7.0, rng),
            noisy(0.58, 0.025, rng),
            noisy(0.67, 0.025, rng),
            noisy(0.0, 0.006, rng),
            noisy(0.015, 0.01, rng),
            noisy(0.88, 0.06, rng),
            noisy(0.78, 0.06, rng),
        ])

    return clip_sequence(np.array(sequence[:window_size], dtype=float))


def make_normal_sequence(window_size: int, rng: np.random.Generator) -> np.ndarray:
    activity = rng.choice(["standing", "walking", "sitting", "sleeping", "slow_lie_down"])
    sequence = []

    for t in range(window_size):
        phase = t / max(1, window_size - 1)
        if activity == "standing":
            row = [
                noisy(0.33, 0.025, rng),
                noisy(6.0, 4.0, rng),
                noisy(0.20, 0.025, rng),
                noisy(0.38, 0.025, rng),
                noisy(0.0, 0.006, rng),
                noisy(0.025, 0.012, rng),
                noisy(0.82, 0.08, rng),
                noisy(0.20, 0.05, rng),
            ]
        elif activity == "walking":
            wave = np.sin(t * 0.55)
            row = [
                noisy(0.37 + 0.035 * wave, 0.025, rng),
                noisy(10.0 + 5.0 * wave, 4.0, rng),
                noisy(0.23 + 0.025 * wave, 0.025, rng),
                noisy(0.42 + 0.035 * wave, 0.025, rng),
                noisy(0.006 + 0.008 * max(0.0, wave), 0.006, rng),
                noisy(0.10, 0.035, rng),
                noisy(0.50, 0.10, rng),
                noisy(0.28, 0.05, rng),
            ]
        elif activity == "sitting":
            row = [
                noisy(0.52, 0.025, rng),
                noisy(24.0, 6.0, rng),
                noisy(0.37, 0.025, rng),
                noisy(0.56, 0.025, rng),
                noisy(0.0, 0.006, rng),
                noisy(0.025, 0.012, rng),
                noisy(0.82, 0.07, rng),
                noisy(0.46, 0.06, rng),
            ]
        elif activity == "sleeping":
            row = [
                noisy(0.68, 0.02, rng),
                noisy(72.0, 6.0, rng),
                noisy(0.58, 0.025, rng),
                noisy(0.67, 0.025, rng),
                noisy(0.0, 0.004, rng),
                noisy(0.01, 0.006, rng),
                noisy(0.93, 0.04, rng),
                noisy(0.78, 0.05, rng),
            ]
        else:
            row = [
                noisy(0.34 + phase * 0.32, 0.02, rng),
                noisy(7.0 + phase * 62.0, 5.0, rng),
                noisy(0.21 + phase * 0.36, 0.02, rng),
                noisy(0.39 + phase * 0.27, 0.02, rng),
                noisy(0.006 + phase * 0.010, 0.004, rng),
                noisy(0.045, 0.018, rng),
                noisy(0.74, 0.08, rng),
                noisy(0.20 + phase * 0.55, 0.05, rng),
            ]
        sequence.append(row)

    return clip_sequence(np.array(sequence, dtype=float))


def synthetic_dataset(n_samples: int, window_size: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    sequences = []
    labels = []

    for _ in range(n_samples):
        is_fall = rng.random() < 0.42
        if is_fall:
            sequences.append(make_fall_sequence(window_size, rng).flatten())
            labels.append(1)
        else:
            sequences.append(make_normal_sequence(window_size, rng).flatten())
            labels.append(0)

    return np.array(sequences, dtype=float), np.array(labels, dtype=int)


def infer_path_label(path: Path) -> int | None:
    lowered = " ".join(part.lower() for part in path.parts)
    name = path.name.lower()
    if "adl" in lowered or "normal" in lowered:
        return 0
    if "fall" in lowered:
        return 1
    if name.startswith("fall-"):
        return 1
    if name.startswith("adl-"):
        return 0
    return None


def find_dataset_files(data_dir: Path) -> list[Path]:
    files = []
    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            files.append(path)
        elif suffix == ".zip" and "rgb" in path.name.lower():
            files.append(path)
    return sorted(files)


def window_has_fall_transition(sequence: np.ndarray) -> bool:
    centroid = sequence[:, 0]
    head = sequence[:, 2]
    velocity = sequence[:, 4]
    motion = sequence[:, 5]
    ground = sequence[:, 7]
    return bool(
        np.max(velocity) > 0.026
        and (centroid[-1] - centroid[0] > 0.09 or head[-1] - head[0] > 0.08)
        and (np.max(motion) > 0.08 or ground[-1] > 0.48)
    )


def make_windows(
    features: list[list[float]],
    source_label: int,
    window_size: int,
    stride: int,
) -> tuple[list[np.ndarray], list[int]]:
    windows = []
    labels = []
    if len(features) < window_size:
        return windows, labels

    array = np.array(features, dtype=float)
    for start in range(0, len(array) - window_size + 1, stride):
        window = array[start:start + window_size]
        if source_label == 1:
            label = 1 if window_has_fall_transition(window) else 0
        else:
            label = 0
        windows.append(window.flatten())
        labels.append(label)

    return windows, labels


def frames_from_video(path: Path) -> Iterable[np.ndarray]:
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame
    finally:
        cap.release()


def frames_from_zip(path: Path) -> Iterable[np.ndarray]:
    import cv2

    with zipfile.ZipFile(path) as archive:
        image_names = sorted(
            name for name in archive.namelist()
            if Path(name).suffix.lower() in IMAGE_EXTENSIONS
        )
        for name in image_names:
            data = np.frombuffer(archive.read(name), dtype=np.uint8)
            frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if frame is not None:
                yield frame


def extract_real_dataset(
    data_dir: Path,
    window_size: int,
    stride: int,
    frame_step: int,
    max_files: int | None,
) -> tuple[np.ndarray, np.ndarray]:
    try:
        from app.features import FeatureExtractor
        from app.vision import PoseTracker
    except Exception as exc:
        print(f"Skipping real dataset extraction: app vision import failed ({exc})")
        return np.empty((0, window_size * len(FEATURE_NAMES))), np.empty((0,), dtype=int)

    files = find_dataset_files(data_dir)
    if max_files is not None:
        files = files[:max_files]

    all_windows: list[np.ndarray] = []
    all_labels: list[int] = []

    for file_idx, path in enumerate(files, start=1):
        source_label = infer_path_label(path)
        if source_label is None:
            continue

        print(f"[{file_idx}/{len(files)}] extracting {path.name}", flush=True)
        tracker = PoseTracker(num_poses=1, min_detection_confidence=0.35, min_tracking_confidence=0.35)
        extractor = FeatureExtractor()
        features: list[list[float]] = []

        try:
            frame_iter = frames_from_zip(path) if path.suffix.lower() == ".zip" else frames_from_video(path)
            for frame_idx, frame in enumerate(frame_iter):
                if frame_idx % frame_step != 0:
                    continue
                _, poses = tracker.process_frame(frame, draw_overlay=False)
                if not poses:
                    continue
                frame_features = extractor.extract(poses[0])
                if frame_features.pose_reliable:
                    features.append(feature_vector(frame_features))
        except Exception as exc:
            print(f"  skipped: {exc}", flush=True)
        finally:
            tracker.close()

        windows, labels = make_windows(features, source_label, window_size, stride)
        all_windows.extend(windows)
        all_labels.extend(labels)
        print(f"  windows: {len(windows)}", flush=True)

    if not all_windows:
        return np.empty((0, window_size * len(FEATURE_NAMES))), np.empty((0,), dtype=int)

    return np.array(all_windows, dtype=float), np.array(all_labels, dtype=int)


def train_model(X: np.ndarray, y: np.ndarray, seed: int) -> tuple[MLPClassifier, StandardScaler, dict[str, float]]:
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled,
        y,
        test_size=0.22,
        random_state=seed,
        stratify=y,
    )

    model = MLPClassifier(
        hidden_layer_sizes=(128, 64, 32),
        activation="relu",
        solver="adam",
        alpha=0.0008,
        batch_size=64,
        learning_rate_init=0.001,
        max_iter=250,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=20,
        random_state=seed,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
    }
    return model, scaler, metrics


def save_model(
    output_path: Path,
    model: MLPClassifier,
    scaler: StandardScaler,
    metrics: dict[str, float],
    window_size: int,
    sources: list[str],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        pickle.dump(
            {
                "model": model,
                "scaler": scaler,
                "window_size": window_size,
                "feature_names": FEATURE_NAMES,
                "metrics": metrics,
                "sources": sources,
            },
            f,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train FallGuard model")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("app/models/fall_detector.pkl"))
    parser.add_argument("--window-size", type=int, default=30)
    parser.add_argument("--stride", type=int, default=5)
    parser.add_argument("--frame-step", type=int, default=3)
    parser.add_argument("--synthetic-samples", type=int, default=2400)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-files", type=int, default=None)
    args = parser.parse_args()

    X_syn, y_syn = synthetic_dataset(args.synthetic_samples, args.window_size, args.seed)
    sources = [f"synthetic_hard_negatives:{len(y_syn)}"]
    arrays = [X_syn]
    labels = [y_syn]

    if args.data_dir is not None and args.data_dir.exists():
        X_real, y_real = extract_real_dataset(
            args.data_dir,
            args.window_size,
            args.stride,
            max(1, args.frame_step),
            args.max_files,
        )
        if len(y_real):
            arrays.append(X_real)
            labels.append(y_real)
            sources.append(f"real_dataset:{args.data_dir}:{len(y_real)}")
    elif args.data_dir is not None:
        print(f"Dataset folder not found: {args.data_dir}")

    X = np.vstack(arrays)
    y = np.concatenate(labels)

    if len(set(y.tolist())) < 2:
        raise RuntimeError("Training needs both fall and non-fall examples.")

    print(f"Training samples: {len(y)}")
    print(f"Fall samples: {int(np.sum(y == 1))}")
    print(f"Non-fall samples: {int(np.sum(y == 0))}")

    model, scaler, metrics = train_model(X, y, args.seed)
    save_model(args.output, model, scaler, metrics, args.window_size, sources)

    print("Metrics:")
    for name, value in metrics.items():
        print(f"  {name}: {value:.3f}")
    print(f"Saved: {args.output}")
    print("Sources:")
    for source in sources:
        print(f"  {source}")


if __name__ == "__main__":
    main()
