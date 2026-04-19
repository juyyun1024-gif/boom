"""Training script for fall detection LSTM model.

This script trains a simple LSTM model on fall detection data.
Run this separately from the main application.

Usage:
    python train_fall_model.py
"""

import numpy as np
import pickle
from pathlib import Path

# Check if we have the required libraries
try:
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    print("✓ scikit-learn available")
except ImportError:
    print("⚠ scikit-learn not installed. Run: pip install scikit-learn")
    exit(1)

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    print(f"✓ TensorFlow {tf.__version__} available")
except ImportError:
    print("⚠ TensorFlow not installed. Run: pip install tensorflow")
    exit(1)


def generate_synthetic_fall_data(n_samples=500, window_size=30):
    """Generate synthetic fall detection data for training.
    
    In production, this would be replaced with real fall detection dataset.
    For now, we generate realistic synthetic data based on fall physics.
    
    Args:
        n_samples: Number of sequences to generate
        window_size: Length of each sequence
        
    Returns:
        X: Feature sequences (n_samples, window_size, n_features)
        y: Labels (n_samples,) - 0=normal, 1=fall
    """
    print(f"\n📊 Generating {n_samples} synthetic training samples...")
    
    n_features = 8  # body_centroid_y, torso_angle, head_height, etc.
    X = []
    y = []
    
    # Generate fall sequences (50% of data)
    for _ in range(n_samples // 2):
        sequence = []
        
        # Start: standing position
        for t in range(10):
            features = [
                0.3 + np.random.normal(0, 0.02),  # body_centroid_y (low = standing)
                5 + np.random.normal(0, 3),        # torso_angle (upright)
                0.2 + np.random.normal(0, 0.02),   # head_height (high)
                0.35 + np.random.normal(0, 0.02),  # hip_height
                0.0 + np.random.normal(0, 0.005),  # velocity (minimal)
                0.02 + np.random.normal(0, 0.01),  # motion_energy
                0.8 + np.random.normal(0, 0.1),    # stillness_score
                0.2 + np.random.normal(0, 0.05),   # ground_proximity (low)
            ]
            sequence.append(features)
        
        # Fall: rapid descent
        for t in range(10, 20):
            progress = (t - 10) / 10
            features = [
                0.3 + progress * 0.4 + np.random.normal(0, 0.02),  # descending
                5 + progress * 60 + np.random.normal(0, 5),         # tilting
                0.2 - progress * 0.15 + np.random.normal(0, 0.02),  # head dropping
                0.35 + progress * 0.3 + np.random.normal(0, 0.02),  # hips dropping
                0.05 + progress * 0.05 + np.random.normal(0, 0.01), # high velocity
                0.3 + progress * 0.2 + np.random.normal(0, 0.05),   # high motion
                0.2 - progress * 0.15 + np.random.normal(0, 0.05),  # low stillness
                0.2 + progress * 0.6 + np.random.normal(0, 0.05),   # high ground prox
            ]
            sequence.append(features)
        
        # After fall: on ground
        for t in range(20, window_size):
            features = [
                0.7 + np.random.normal(0, 0.02),   # high centroid (on ground)
                70 + np.random.normal(0, 5),        # horizontal
                0.6 + np.random.normal(0, 0.02),    # low head
                0.65 + np.random.normal(0, 0.02),   # low hips
                0.0 + np.random.normal(0, 0.005),   # no velocity
                0.01 + np.random.normal(0, 0.005),  # minimal motion
                0.9 + np.random.normal(0, 0.05),    # high stillness
                0.85 + np.random.normal(0, 0.05),   # very high ground prox
            ]
            sequence.append(features)
        
        X.append(sequence)
        y.append(1)  # Fall
    
    # Generate normal sequences (50% of data)
    for _ in range(n_samples // 2):
        sequence = []
        activity = np.random.choice(['standing', 'walking', 'sitting'])
        
        if activity == 'standing':
            for t in range(window_size):
                features = [
                    0.3 + np.random.normal(0, 0.03),
                    5 + np.random.normal(0, 5),
                    0.2 + np.random.normal(0, 0.03),
                    0.35 + np.random.normal(0, 0.03),
                    0.0 + np.random.normal(0, 0.01),
                    0.02 + np.random.normal(0, 0.01),
                    0.8 + np.random.normal(0, 0.1),
                    0.2 + np.random.normal(0, 0.05),
                ]
                sequence.append(features)
        
        elif activity == 'walking':
            for t in range(window_size):
                features = [
                    0.35 + 0.05 * np.sin(t * 0.5) + np.random.normal(0, 0.02),
                    10 + 5 * np.sin(t * 0.5) + np.random.normal(0, 3),
                    0.25 + 0.03 * np.sin(t * 0.5) + np.random.normal(0, 0.02),
                    0.4 + 0.05 * np.sin(t * 0.5) + np.random.normal(0, 0.02),
                    0.01 + np.random.normal(0, 0.005),
                    0.1 + np.random.normal(0, 0.02),
                    0.5 + np.random.normal(0, 0.1),
                    0.3 + np.random.normal(0, 0.05),
                ]
                sequence.append(features)
        
        else:  # sitting
            for t in range(window_size):
                features = [
                    0.55 + np.random.normal(0, 0.02),
                    30 + np.random.normal(0, 5),
                    0.45 + np.random.normal(0, 0.02),
                    0.55 + np.random.normal(0, 0.02),
                    0.0 + np.random.normal(0, 0.005),
                    0.01 + np.random.normal(0, 0.01),
                    0.85 + np.random.normal(0, 0.05),
                    0.55 + np.random.normal(0, 0.05),
                ]
                sequence.append(features)
        
        X.append(sequence)
        y.append(0)  # Normal
    
    X = np.array(X)
    y = np.array(y)
    
    print(f"✓ Generated data shape: X={X.shape}, y={y.shape}")
    print(f"  Falls: {np.sum(y)} | Normal: {len(y) - np.sum(y)}")
    
    return X, y


def build_lstm_model(window_size=30, n_features=8):
    """Build LSTM model for fall detection.
    
    Args:
        window_size: Length of input sequences
        n_features: Number of features per timestep
        
    Returns:
        Compiled Keras model
    """
    print("\n🏗️  Building LSTM model...")
    
    model = keras.Sequential([
        layers.Input(shape=(window_size, n_features)),
        layers.LSTM(64, return_sequences=True),
        layers.Dropout(0.3),
        layers.LSTM(32),
        layers.Dropout(0.3),
        layers.Dense(16, activation='relu'),
        layers.Dense(1, activation='sigmoid')
    ])
    
    model.compile(
        optimizer='adam',
        loss='binary_crossentropy',
        metrics=['accuracy', keras.metrics.Precision(), keras.metrics.Recall()]
    )
    
    print("✓ Model built")
    model.summary()
    
    return model


def train_model():
    """Main training function."""
    print("=" * 60)
    print("🚀 Fall Detection Model Training")
    print("=" * 60)
    
    # Generate data
    X, y = generate_synthetic_fall_data(n_samples=1000, window_size=30)
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\n📊 Train: {len(X_train)} | Test: {len(X_test)}")
    
    # Build model
    model = build_lstm_model(window_size=30, n_features=8)
    
    # Train
    print("\n🎯 Training model...")
    history = model.fit(
        X_train, y_train,
        validation_split=0.2,
        epochs=30,
        batch_size=32,
        verbose=1
    )
    
    # Evaluate
    print("\n📈 Evaluating on test set...")
    test_loss, test_acc, test_prec, test_recall = model.evaluate(X_test, y_test)
    print(f"\n✓ Test Accuracy: {test_acc:.3f}")
    print(f"✓ Test Precision: {test_prec:.3f}")
    print(f"✓ Test Recall: {test_recall:.3f}")
    
    # Save model
    model_dir = Path(__file__).parent / "app" / "models"
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / "fall_detection_lstm.h5"
    
    model.save(model_path)
    print(f"\n💾 Model saved to: {model_path}")
    
    # Also save as pickle for easier loading
    pickle_path = model_dir / "fall_detection_lstm.pkl"
    with open(pickle_path, 'wb') as f:
        pickle.dump(model, f)
    print(f"💾 Model also saved as: {pickle_path}")
    
    print("\n" + "=" * 60)
    print("✅ Training complete!")
    print("=" * 60)
    print("\nTo use the trained model:")
    print("1. Update config: use_trained_model=True")
    print("2. Restart backend")
    print("3. The model will automatically load")


if __name__ == "__main__":
    train_model()
