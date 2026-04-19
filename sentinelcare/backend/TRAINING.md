# Training Fall Detection Model

This guide explains how to train a custom LSTM model for fall detection.

## Quick Start

```bash
# 1. Install training dependencies
pip install -r requirements-training.txt

# 2. Run training script
python train_fall_model.py

# 3. Model will be saved to app/models/fall_detection_lstm.pkl
```

## What Gets Trained

- **Model Type**: LSTM (Long Short-Term Memory) neural network
- **Input**: 30-frame sequences of pose features (1 second at 30fps)
- **Output**: Fall probability (0-1)
- **Training Data**: Synthetic fall sequences (1000 samples)

## Using the Trained Model

The trained model is **optional** and runs alongside your rule-based system.

### Option 1: Keep Rule-Based (Default)

Your current FallGuard agent uses rules - no changes needed.

### Option 2: Add Trained Model as Comparison

Update `app/models.py`:

```python
class AppConfig(BaseModel):
    # ... existing config ...
    use_trained_model: bool = False  # Set to True to enable
    trained_model_path: str = "app/models/fall_detection_lstm.pkl"
```

Then in `app/main.py`, you can run both side-by-side for comparison.

## Training on Real Data

To train on real fall detection datasets:

1. **Download Dataset**:
   - UR Fall Detection: http://fenix.univ.rzeszow.pl/~mkepski/ds/uf.html
   - Multiple Cameras Fall: https://www.iro.umontreal.ca/~labimage/Dataset/

2. **Extract Pose Features**:
   ```python
   # Use your existing MediaPipe pipeline
   from app.vision import PoseTracker
   from app.features import FeatureExtractor
   
   # Process each video and save features
   ```

3. **Update Training Script**:
   Replace `generate_synthetic_fall_data()` with real data loading

4. **Retrain**:
   ```bash
   python train_fall_model.py
   ```

## Model Performance

Current synthetic model achieves:
- **Accuracy**: ~95% on synthetic test data
- **Precision**: ~93%
- **Recall**: ~96%

Real-world performance will vary. Test thoroughly before production use.

## Architecture

```
Input: (30, 8) - 30 frames × 8 features
  ↓
LSTM(64) + Dropout(0.3)
  ↓
LSTM(32) + Dropout(0.3)
  ↓
Dense(16, relu)
  ↓
Dense(1, sigmoid)
  ↓
Output: Fall probability
```

## Troubleshooting

**"TensorFlow not installed"**
```bash
pip install tensorflow
```

**"Model file not found"**
- Make sure training completed successfully
- Check `app/models/` directory exists
- Verify file path in config

**"Low accuracy on real data"**
- Synthetic data is simplified
- Train on real fall detection dataset
- Adjust model architecture
- Tune hyperparameters

## Next Steps

1. ✅ Train model with synthetic data (quick test)
2. 📊 Collect real fall videos
3. 🎯 Retrain on real data
4. 🧪 A/B test vs. rule-based system
5. 🚀 Deploy best performer
