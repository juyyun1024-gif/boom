# How to Run test2_dataset.py — Fall Detection Video Visualizer

## What it does

`test2_dataset.py` processes MP4 video files through the 5-feature fall detection pipeline and outputs **annotated result MP4 files** with:
- Pose skeleton overlay
- State banner (NORMAL / SUSPICIOUS / MONITORING / CRITICAL ALERT)
- Confidence and Posture Score bars
- Feature readouts (Body Angle, CoG Height, Aspect Ratio, Motion, Stillness)
- Recovery timer countdown
- Red pulsing border on CRITICAL ALERT

---

## Prerequisites

- Python 3.10
- pip
- MediaPipe pose model (`pose_landmarker.task`)

---

## Setup (first time only)

### 1. File structure

These files must be inside `sentinelcare/backend/app/`:

```
sentinelcare/backend/
├── app/
│   ├── __init__.py
│   ├── models.py
│   ├── features.py
│   ├── agent.py
│   ├── vision.py
│   ├── main.py
│   └── event_store.py
├── test_dataset.py
├── test2_dataset.py
├── requirements.txt
├── pose_landmarker.task
└── datasets/
    └── sample/
        ├── 01.mp4
        ├── 02.mp4
        └── ...
```

> **Important:** The Python files in this folder (`fall_detection_files/`) need to be placed into the correct `sentinelcare/backend/` structure. Copy them like this:
>
> - `models.py`, `features.py`, `agent.py`, `vision.py`, `main.py`, `event_store.py`, `__init__.py` → into `sentinelcare/backend/app/`
> - `test_dataset.py`, `test2_dataset.py`, `requirements.txt` → into `sentinelcare/backend/`

### 2. Create virtual environment & install dependencies

```powershell
cd sentinelcare\backend

# Create venv
"C:\Users\kousuke mine\AppData\Local\Programs\Python\Python310\python.exe" -m venv venv

# Install dependencies
.\venv\Scripts\pip.exe install -r requirements.txt
```

### 3. Download MediaPipe pose model

```powershell
.\venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task', 'pose_landmarker.task'); print('Done!')"
```

> If the model fails to load (Japanese characters in path):
> ```powershell
> Copy-Item pose_landmarker.task "$env:TEMP\pose_landmarker.task"
> ```

---

## Running test2_dataset.py

### From project root (`boom/`):

```powershell
# Process a single video → outputs result_01.mp4
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test2_dataset.py" "sentinelcare\backend\datasets\sample\01.mp4"

# Process all videos in a folder
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test2_dataset.py" "sentinelcare\backend\datasets\sample"

# Custom output folder
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test2_dataset.py" "sentinelcare\backend\datasets\sample" --out "sentinelcare\backend\datasets\my_results"
```

### From `sentinelcare/backend/`:

```powershell
cd sentinelcare\backend

# Single video
.\venv\Scripts\python.exe test2_dataset.py datasets\sample\01.mp4

# All videos in folder
.\venv\Scripts\python.exe test2_dataset.py datasets\sample

# Custom output folder
.\venv\Scripts\python.exe test2_dataset.py datasets\sample --out datasets\my_results
```

---

## Output

Result videos are saved to `datasets/sample/results_video/` (or your custom `--out` path):

```
datasets/sample/results_video/
├── result_01.mp4
├── result_02.mp4
├── result_03.mp4
└── ...
```

Open them in any video player (VLC, Windows Media Player).

---

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `--recovery-window` | Seconds before CRITICAL ALERT (3–60) | 5.0 |
| `--threshold` | Fall confidence threshold (0.1–0.95) | 0.45 |
| `--window-size` | Sliding window frames (5–60) | 20 |
| `--stillness` | Stillness threshold (0.001–0.05) | 0.005 |
| `--ema` | EMA smoothing alpha (0.05–0.5) | 0.3 |

### Example with custom parameters:

```powershell
.\venv\Scripts\python.exe test2_dataset.py datasets\sample --recovery-window 3 --threshold 0.4
```

---

## Also: test_dataset.py (terminal output only)

If you just want text results without generating video files:

```powershell
# Terminal output only (faster)
.\venv\Scripts\python.exe test_dataset.py datasets\sample

# With live playback window
.\venv\Scripts\python.exe test_dataset.py datasets\sample --show
```
