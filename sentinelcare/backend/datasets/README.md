# Datasets for SentinelCare Testing

Place downloaded `.mp4` / `.avi` video files in this folder.

## Recommended Datasets

### 1. Thermal Mannequin Fall (MP4 videos, easiest to use)
- **URL:** https://www.kaggle.com/datasets/ivannikolov/thermal-mannequin-fall-image-dataset
- Contains MP4 thermal videos of mannequin falls
- Download → extract → copy `.mp4` files here

### 2. CCTV Incident Dataset (Fall & Lying Down)
- **URL:** https://www.kaggle.com/datasets/simuletic/cctv-incident-dataset-fall-and-lying-down-detection
- CCTV footage with fall and lying down incidents

### 3. Human Fall Detection Dataset
- **URL:** https://www.kaggle.com/datasets/uttejkumarkandagatla/fall-detection-dat
- Various human fall scenarios

### 4. UR Fall Detection Dataset
- **URL:** https://fenix.ur.edu.pl/mkepski/ds/uf.html
- Academic dataset with fall and daily activity videos

## Folder Structure

```
datasets/
├── README.md          (this file)
├── fall_01.mp4
├── fall_02.mp4
├── normal_01.mp4
└── subfolder/         (subfolders are also scanned)
    └── video.avi
```

## How to Run

```bash
cd sentinelcare/backend
conda activate sentinelcare

# Test all videos in datasets/
python test_dataset.py

# Test a single video
python test_dataset.py datasets/fall_01.mp4

# Show video playback with skeleton overlay
python test_dataset.py --show

# Adjust detection parameters
python test_dataset.py --threshold 0.5 --recovery-window 15
```
