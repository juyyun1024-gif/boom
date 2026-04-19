# How to Run SentinelCare — 5-Feature Fall Detection

## Prerequisites

- Python 3.10
- pip

---

## 1. Setup (first time only)

### Create virtual environment & install dependencies

```powershell
cd sentinelcare\backend

# Create venv with Python 3.10
"C:\Users\kousuke mine\AppData\Local\Programs\Python\Python310\python.exe" -m venv venv

# Install dependencies
.\venv\Scripts\pip.exe install -r requirements.txt
```

### Download MediaPipe pose model

```powershell
.\venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task', 'pose_landmarker.task'); print('Done!')"
```

> **Note:** If the model fails to load due to Japanese characters or spaces in your path:
> ```powershell
> Copy-Item pose_landmarker.task "$env:TEMP\pose_landmarker.task"
> ```

---

## 2. Detection Method

The system uses **5 core features** computed from pose landmarks, comparing frame-to-frame differences:

| # | Feature | What it measures |
|---|---------|-----------------|
| 1 | **Body Axis Angle** | Shoulder→hip deviation from vertical (0°=upright, 90°=horizontal) |
| 2 | **Center of Gravity Height** | How low the body is in the frame |
| 3 | **Aspect Ratio** | Body bounding box shape (tall=standing, wide=lying) |
| 4 | **Sudden Motion Change** | Landmark displacement between consecutive frames |
| 5 | **Stillness Duration** | How long the person has been motionless |

These combine into a **Posture Score** (single-frame) and **Cumulative Delta** (sliding window) to detect both active falls and already-fallen states.

Key improvements over the old velocity-gated approach:
- Works on static images (no motion required)
- No flickering between states (EMA smoothing + consecutive-frame gating)
- Detects both falling motion AND already-collapsed posture

---

## 3. Run Fall Detection on Videos

From the **project root** (`boom/`):

```powershell
# Test all videos + images in datasets/
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test_dataset.py" "sentinelcare\backend\datasets"

# Test a single video
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test_dataset.py" "sentinelcare\backend\datasets\sample\sample_1.mp4"

# Test a single image (posture score only)
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test_dataset.py" "sentinelcare\backend\datasets\laying01.png"

# Show live playback with skeleton overlay
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test_dataset.py" "sentinelcare\backend\datasets" --show
```

Or from `sentinelcare/backend/`:

```powershell
cd sentinelcare\backend

.\venv\Scripts\python.exe test_dataset.py datasets
.\venv\Scripts\python.exe test_dataset.py datasets\sample\sample_1.mp4
.\venv\Scripts\python.exe test_dataset.py datasets --show
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--show` | Show video playback with pose skeleton overlay | off |
| `--threshold` | Fall confidence threshold (0.1–0.95) | 0.55 |
| `--recovery-window` | Seconds to wait for recovery before alert (3–60) | 10.0 |
| `--window-size` | Sliding window size in frames (5–60) | 20 |
| `--stillness` | Stillness threshold (0.001–0.05) | 0.005 |
| `--ema` | EMA smoothing alpha (0.05–0.5) | 0.3 |
| `--fps` | FPS for image sequences | 25.0 |

### Controls (when using `--show`)

- **Q** — quit
- **Space** — pause/resume

---

## 4. Generate Annotated Result Videos

Creates MP4 files with skeleton overlay, state banners, confidence bars, and feature readouts burned into each frame.

```powershell
# From project root — process sample videos
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test2_dataset.py" "sentinelcare\backend\datasets\sample"

# Process a single video
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test2_dataset.py" "sentinelcare\backend\datasets\sample\sample_1.mp4"
```

Output files are saved to `datasets/sample/results_video/result_*.mp4`. Open them in any video player (VLC, Windows Media Player).

---

## 5. Run Full App (Backend + Frontend)

### Terminal 1 — Backend

```powershell
cd sentinelcare\backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2 — Frontend

```powershell
cd sentinelcare\frontend
npm install   # first time only
npm run dev
```

Open **http://localhost:3000**

---

## 6. Adding Test Datasets

Place `.mp4` / `.avi` video files in `datasets/`:

```
datasets/
├── sample/
│   ├── sample_1.mp4
│   └── sample_2.mp4
├── laying01.png ... laying24.png
└── your_new_video.mp4
```

Recommended dataset sources:
- [CCTV Incident Dataset](https://www.kaggle.com/datasets/simuletic/cctv-incident-dataset-fall-and-lying-down-detection)
- [Human Fall Detection](https://www.kaggle.com/datasets/uttejkumarkandagatla/fall-detection-dat)
- [UR Fall Detection](https://fenix.ur.edu.pl/mkepski/ds/uf.html)

---

## 7. State Machine

The detection follows this state flow:

```
NORMAL → SUSPICIOUS_EVENT → MONITORING_RECOVERY → CRITICAL_ALERT
                                    ↓
                                RECOVERED → NORMAL
```

- **NORMAL**: No fall detected
- **SUSPICIOUS_EVENT**: High posture score for 3+ consecutive frames
- **MONITORING_RECOVERY**: Confirmed suspicious, waiting for person to get up
- **CRITICAL_ALERT**: Person didn't recover within the recovery window
- **RECOVERED**: Person got back up

---

## Troubleshooting

### "pose_landmarker.task not found"
Download the model (see step 1).

### "Unable to open file at ... pose_landmarker.task"
Path contains Japanese characters or spaces. Copy the model:
```powershell
Copy-Item sentinelcare\backend\pose_landmarker.task "$env:TEMP\pose_landmarker.task"
```

### All videos show "NORMAL" with 0% confidence
MediaPipe can't detect poses in the video. This happens with:
- Thermal / infrared videos
- Very low resolution footage
- Videos where the person is too small

Try regular camera footage datasets instead.

### conda not working
If conda has path issues (spaces in username), use venv instead as shown above.
