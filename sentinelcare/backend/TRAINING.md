# Training FallGuard

FallGuard loads this model by default:

```bash
app/models/fall_detector.pkl
```

## Train Now

From `sentinelcare/backend`:

```bash
python train_fallguard_model.py
```

This trains with synthetic fall sequences plus hard negatives for:

- sleeping / already lying down
- slow lie-down
- standing, walking, sitting

## Train With UR Fall

Download the UR Fall cam0 MP4 files into a folder:

```bash
python download_urfall_mp4.py --output-dir /tmp/sentinelcare_urfall_mp4
```

Then run:

```bash
python train_fallguard_model.py --data-dir /tmp/sentinelcare_urfall_mp4 --frame-step 3
```

The trainer uses the same MediaPipe pose pipeline as the live app, keeps only
reliable full-body frames, and labels fall-video windows as positive only when
they contain a fast fall-like transition.

## Why UR Fall First

UR Fall has 30 fall sequences and 40 activities of daily living with RGB data.
That matches our webcam pipeline better than skeleton-only data.

License note: UR Fall is intended for non-commercial academic use.
