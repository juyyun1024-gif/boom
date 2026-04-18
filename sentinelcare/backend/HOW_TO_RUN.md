# How to Run SentinelCare Dataset Tester

## Prerequisites

- Python 3.10
- pip

---

## 1. Setup (first time only)

### Create virtual environment & install dependencies

```powershell
# Move to backend folder
cd sentinelcare\backend

# Create venv with Python 3.10
# (adjust the path to your Python 3.10 if different)
"C:\Users\kousuke mine\AppData\Local\Programs\Python\Python310\python.exe" -m venv venv

# Install dependencies
.\venv\Scripts\pip.exe install -r requirements.txt
```

### Download MediaPipe pose model

```powershell
.\venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task', 'pose_landmarker.task'); print('Done!')"
```

> **Note:** If the model fails to load due to Japanese characters or spaces in your path, copy it to a simpler location:
> ```powershell
> Copy-Item pose_landmarker.task "$env:TEMP\pose_landmarker.task"
> ```
> The code will automatically find it there.

---

## 2. Run Dataset Test

From the **project root** (`boom/`):

```powershell
# Test all videos in datasets/ (terminal output only)
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test_dataset.py" "sentinelcare\backend\datasets"

# Test with video playback + skeleton overlay
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test_dataset.py" "sentinelcare\backend\datasets" --show

# Test a single video
& "sentinelcare\backend\venv\Scripts\python.exe" "sentinelcare\backend\test_dataset.py" "sentinelcare\backend\datasets\fall_01.mp4"
```

Or from `sentinelcare/backend/`:

```powershell
cd sentinelcare\backend

# Test all
.\venv\Scripts\python.exe test_dataset.py datasets

# Test with video playback
.\venv\Scripts\python.exe test_dataset.py datasets --show

# Test single video
.\venv\Scripts\python.exe test_dataset.py datasets\fall_01.mp4 --show
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--show` | Show video playback with pose skeleton overlay | off |
| `--threshold` | Fall confidence threshold (0.0 - 1.0) | 0.55 |
| `--recovery-window` | Seconds to wait for recovery before alert | 10.0 |

### Controls (when using `--show`)

- **Q** — quit
- **Space** — pause/resume

---

## 3. Run Full App (Backend + Frontend)

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

## Dataset Videos

Currently included in `datasets/`:

| File | Description |
|------|-------------|
| `fall_01.mp4` | Thermal mannequin fall scenario |
| `fall_02.mp4` | Thermal mannequin fall scenario |
| `fall_03.mp4` | Thermal mannequin fall scenario |

### Adding more datasets

Download from these sources and place `.mp4` files in `datasets/`:

- [CCTV Incident Dataset](https://www.kaggle.com/datasets/simuletic/cctv-incident-dataset-fall-and-lying-down-detection)
- [Human Fall Detection](https://www.kaggle.com/datasets/uttejkumarkandagatla/fall-detection-dat)
- [UR Fall Detection](https://fenix.ur.edu.pl/mkepski/ds/uf.html)

> **Tip:** Thermal videos may not work well with MediaPipe pose detection. Regular camera / CCTV footage gives better results.

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
