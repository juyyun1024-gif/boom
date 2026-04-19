"""Simple fall detection model training without TensorFlow.

Uses scikit-learn's MLPClassifier (neural network) instead of TensorFlow
to avoid dependency conflicts.
"""

import numpy as np
import pickle
from pathlib import Path
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

print("=" * 60)
print("🚀 Simple Fall Detection Model Training")
print("=" * 60)


def generate_fall_sequences(n_samples=500, window_size=30):
    """Generate synthetic fall detection sequences."""
    print(f"\n📊 Generating {n_samples} training samples...")
    
    n_features = 8
    X = []
    y = []
    
    # Generate fall sequences (50%)
    for _ in range(n_samples // 2):
        sequence = []
        
        # Standing (frames 0-10)
        for t in range(10):
            features = [
                0.3 + np.random.normal(0, 0.02),   # body_centroid_y
                5 + np.random.normal(0, 3),         # torso_angle
                0.2 + np.random.normal(0, 0.02),    # head_height
                0.35 + np.random.normal(0, 0.02),   # hip_height
                0.0 + np.random.normal(0, 0.005),   # velocity
                0.02 + np.random.normal(0, 0.01),   # motion_energy
                0.8 + np.random.normal(0, 0.1),     # stillness_score
                0.2 + np.random.normal(0, 0.05),    # ground_proximity
            ]
            sequence.extend(features)
        
        # Falling (frames 10-20)
        for t in range(10, 20):
            progress = (t - 10) / 10
            features = [
                0.3 + progress * 0.4 + np.random.normal(0, 0.02),
                5 + progress * 60 + np.random.normal(0, 5),
                0.2 - progress * 0.15 + np.random.normal(0, 0.02),
                0.35 + progress * 0.3 + np.random.normal(0, 0.02),
                0.05 + progress * 0.05 + np.random.normal(0, 0.01),
                0.3 + progress * 0.2 + np.random.normal(0, 0.05),
                0.2 - progress * 0.15 + np.random.normal(0, 0.05),
                0.2 + progress * 0.6 + np.random.normal(0, 0.05),
            ]
            sequence.extend(features)
        
        # On ground (frames 20-30)
        for t in range(20, window_size):
            features = [
                0.7 + np.random.normal(0, 0.02),
                70 + np.random.normal(0, 5),
                0.6 + np.random.normal(0, 0.02),
                0.65 + np.random.normal(0, 0.02),
                0.0 + np.random.normal(0, 0.005),
                0.01 + np.random.normal(0, 0.005),
                0.9 + np.random.normal(0, 0.05),
                0.85 + np.random.normal(0, 0.05),
            ]
            sequence.extend(features)
        
        X.append(sequence)
        y.append(1)  # Fall
    
    # Generate normal sequences (50%)
    for _ in range(n_samples // 2):
        sequence = []
        activity = np.random.choice(['standing', 'walking', 'sitting'])
        
        for t in range(window_size):
            if activity == 'standing':
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
            elif activity == 'walking':
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
            else:  # sitting
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
            sequence.extend(features)
        
        X.append(sequence)
        y.append(0)  # Normal
    
    X = np.array(X)
    y = np.array(y)
    
    print(f"✓ Generated: X={X.shape}, y={y.shape}")
    print(f"  Falls: {np.sum(y)} | Normal: {len(y) - np.sum(y)}")
    
    return X, y


# Generate data
X, y = generate_fall_sequences(n_samples=1000, window_size=30)

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"\n📊 Train: {len(X_train)} | Test: {len(X_test)}")

# Scale features
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Build neural network
print("\n🏗️  Building neural network...")
model = MLPClassifier(
    hidden_layer_sizes=(128, 64, 32),
    activation='relu',
    solver='adam',
    max_iter=100,
    random_state=42,
    verbose=True
)

# Train
print("\n🎯 Training model...")
model.fit(X_train_scaled, y_train)

# Evaluate
print("\n📈 Evaluating...")
y_pred = model.predict(X_test_scaled)
y_pred_proba = model.predict_proba(X_test_scaled)[:, 1]

accuracy = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred)
recall = recall_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred)

print(f"\n✓ Test Accuracy:  {accuracy:.3f}")
print(f"✓ Test Precision: {precision:.3f}")
print(f"✓ Test Recall:    {recall:.3f}")
print(f"✓ Test F1 Score:  {f1:.3f}")

# Save model
model_dir = Path(__file__).parent / "app" / "models"
model_dir.mkdir(exist_ok=True)

model_path = model_dir / "fall_detector.pkl"
with open(model_path, 'wb') as f:
    pickle.dump({'model': model, 'scaler': scaler}, f)

print(f"\n💾 Model saved to: {model_path}")

print("\n" + "=" * 60)
print("✅ Training complete!")
print("=" * 60)
print("\nModel is ready to use!")
print("The trained model will work with your existing system.")
