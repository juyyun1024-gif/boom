# Requirements Document

## Introduction

SentinelCare's current fall detection system fails on real-world inputs because it relies on instantaneous velocity between frames — a metric that is zero for static images and flickers erratically on video. This rewrite replaces the velocity-gated detection approach with a **frame-to-frame pose comparison** strategy that tracks how a person's posture changes over a sliding window of recent frames, enabling reliable fall detection from video streams.

The new system uses **5 core features** derived from pose landmarks to detect falls and unconsciousness:

| # | Feature (特徴量) | Description | Relation to Fall |
|---|---|---|---|
| 1 | **Body Axis Angle** (体軸の角度) | Shoulder→hip vector deviation from vertical | Sudden change from upright to horizontal |
| 2 | **Center of Gravity Height** (重心高さ) | Y-coordinate average of major landmarks | Rapid drop indicates falling |
| 3 | **Aspect Ratio** (アスペクト比) | Bounding box height÷width ratio | Changes from tall (standing) to wide (lying) |
| 4 | **Sudden Motion Change** (動きの急変度) | Frame-to-frame landmark displacement sum | Rapid acceleration just before a fall |
| 5 | **Stillness Duration** (静止継続時間) | Duration of no/minimal movement | Sustained stillness after falling = unconscious |

These features are computed by comparing the current frame against previous frames in a sliding window, enabling detection of both active falls (features 1–4 change rapidly) and already-fallen/unconscious states (features 1–3 indicate collapsed posture, feature 5 indicates prolonged stillness).

### Key Problems Solved

1. **Static image failure**: The current velocity gate (`if f.velocity < 0.02: return 0.0`) means any single-frame or low-motion input scores zero confidence — laying PNGs never trigger detection.
2. **State machine flickering**: Instantaneous velocity resets frame-to-frame, causing the agent to bounce between SUSPICIOUS and NORMAL instead of accumulating evidence.
3. **Thermal/infrared limitations**: MediaPipe struggles with non-RGB footage. The new architecture isolates the pose estimation layer so alternative backends can be swapped in without changing detection logic.

### Tech Stack Decisions

- **Keep MediaPipe PoseLandmarker** (already installed, ~30MB model, no PyTorch dependency). The 114MB+ PyTorch/YOLOv8 download is impractical on the user's ~400KB/s connection.
- **Keep OpenCV** for video I/O (already installed).
- **Keep FastAPI + WebSocket** backend and **Next.js** frontend — no changes to the streaming architecture.
- **Pure NumPy/math** for all feature computation — no new dependencies required.

## Glossary

### Core Modules
- **Fall_Detector**: The rewritten backend module that analyzes frame-to-frame pose differences to detect falls and unconsciousness from video input.
- **Pose_Estimator**: The module that extracts body landmark coordinates from a video frame (currently MediaPipe PoseLandmarker, designed to be swappable).
- **Feature_Extractor**: The module that computes the 5 core features from raw landmark data, maintaining a sliding window of recent frame history.
- **Fall_Agent**: The state machine that consumes features from the Feature_Extractor and manages transitions between detection states (NORMAL → SUSPICIOUS_EVENT → MONITORING_RECOVERY → RECOVERED | CRITICAL_ALERT).

### 5 Core Detection Features (特徴量)
- **Body_Axis_Angle** (体軸の角度): The angle of the shoulder→hip vector relative to vertical (0° = upright, 90° = horizontal). Computed from the midpoint of left/right shoulders to the midpoint of left/right hips. A sudden increase indicates the person is falling or has fallen.
- **Center_Of_Gravity_Height** (重心高さ): The average Y-coordinate of major landmarks (shoulders, hips, knees). In MediaPipe convention, 0 = top of frame, 1 = bottom. A rapid increase (downward movement) indicates falling; a sustained high value indicates the person is on the ground.
- **Aspect_Ratio** (アスペクト比): The ratio of the bounding box height to width, computed from the min/max x and y coordinates of all visible landmarks. A standing person has a ratio > 1.5 (tall and narrow); a lying person has a ratio < 1.0 (wide and short). A rapid decrease indicates a fall transition.
- **Sudden_Motion_Change** (動きの急変度): The sum of Euclidean distances between each landmark's position in the current frame and the previous frame. A spike in this value indicates rapid body movement (the moment of falling). Computed as frame-to-frame landmark displacement.
- **Stillness_Duration** (静止継続時間): The number of consecutive seconds during which the Sudden_Motion_Change remains below a configured stillness threshold. Sustained stillness after a detected fall indicates unconsciousness or incapacitation.

### Derived Metrics
- **Posture_Score**: A composite metric (0.0–1.0) combining Body_Axis_Angle, Center_Of_Gravity_Height, and Aspect_Ratio to indicate how "collapsed" the current pose is — independent of motion. Computable from a single frame.
- **Cumulative_Delta**: The change in the 5 core features between the current frame and the oldest frame in the Sliding_Window, enabling detection of gradual transitions.
- **Unconsciousness_Score**: A composite metric (0.0–1.0) combining Stillness_Duration, micro-movement absence, posture abnormality, and fall-preceded context to distinguish true unconsciousness from intentional stillness.

### Infrastructure
- **Sliding_Window**: A fixed-size buffer of recent frame features (typically 15–30 frames) used to compute cumulative changes and detect trends rather than relying on single-frame instantaneous values.
- **Stillness_Window**: A secondary sliding window (typically 2–5 seconds of frames) used after a fall is suspected to measure whether the person remains motionless in a collapsed posture.
- **Recovery_Timer**: A countdown timer started when a fall is confirmed, during which the system monitors for signs of the person getting back up.
- **Micro_Movement**: Tiny landmark position variations (standard deviation over a 3–5 second window) caused by breathing, head adjustments, and minor fidgeting that conscious people exhibit even when lying still.
- **Posture_Abnormality**: A metric measuring how unnatural the body's limb arrangement is — limb asymmetry, awkward joint angles, and positions a conscious person would not voluntarily hold.
- **WebSocket_Stream**: The real-time communication channel between the FastAPI backend and the Next.js frontend dashboard.

## Requirements

### Requirement 1: Five Core Features — Frame-to-Frame Computation

**User Story:** As a fall detection system, I want to compute 5 core features from pose landmarks each frame and track their changes over a sliding window, so that I can detect gradual or sudden postural changes that indicate a fall.

#### Acceptance Criteria

1. WHEN a new frame is processed, THE Feature_Extractor SHALL compute all 5 core features: Body_Axis_Angle, Center_Of_Gravity_Height, Aspect_Ratio, Sudden_Motion_Change, and Stillness_Duration.
2. THE Feature_Extractor SHALL maintain a Sliding_Window of the most recent 15 to 30 frames of landmark data and computed features.
3. WHEN the Sliding_Window contains fewer frames than its configured size, THE Feature_Extractor SHALL compute deltas using all available frames.
4. THE Feature_Extractor SHALL compute a Cumulative_Delta for Body_Axis_Angle, Center_Of_Gravity_Height, and Aspect_Ratio by comparing the current frame to the oldest frame in the Sliding_Window.
5. THE Feature_Extractor SHALL compute Sudden_Motion_Change as the sum of Euclidean distances between each landmark's position in the current frame and the previous frame.
6. THE Feature_Extractor SHALL compute Stillness_Duration as the number of consecutive seconds during which Sudden_Motion_Change remains below the configured stillness threshold.
7. WHEN no pose is detected in the current frame, THE Feature_Extractor SHALL retain the last known landmarks in the Sliding_Window and mark the frame as a detection gap.

### Requirement 2: Static Posture Scoring (Velocity-Independent)

**User Story:** As a fall detection system, I want to evaluate the current body posture independently of motion, so that I can detect a person lying on the ground even from a single frame or when there is no motion between frames.

#### Acceptance Criteria

1. THE Feature_Extractor SHALL compute a Posture_Score (0.0 to 1.0) for each frame based on the current pose alone, without requiring motion or velocity data.
2. THE Posture_Score SHALL be a weighted combination of three of the 5 core features: Body_Axis_Angle (deviation from vertical), Center_Of_Gravity_Height (how low the body is in the frame), and Aspect_Ratio (horizontal vs vertical body orientation).
3. WHEN the Body_Axis_Angle exceeds 55 degrees from vertical and the Center_Of_Gravity_Height exceeds 0.6, THE Feature_Extractor SHALL assign a Posture_Score of at least 0.7.
4. WHEN the person is standing upright with a Body_Axis_Angle below 15 degrees, THE Feature_Extractor SHALL assign a Posture_Score below 0.2.
5. WHEN the Aspect_Ratio drops below 1.0 (body wider than tall), THE Feature_Extractor SHALL increase the Posture_Score by at least 0.15.
6. THE Posture_Score SHALL be computable from a single frame without any history, enabling detection on static images.

### Requirement 3: Fall Detection via Combined Features

**User Story:** As a fall detection system, I want to combine static posture scoring with frame-to-frame delta analysis of the 5 core features, so that I can detect both sudden falls (large deltas in features 1–4) and already-fallen states (high posture score from features 1–3, high stillness from feature 5).

#### Acceptance Criteria

1. THE Fall_Agent SHALL use a weighted combination of the Posture_Score (from Body_Axis_Angle, Center_Of_Gravity_Height, Aspect_Ratio) and the Cumulative_Delta (changes in those features over the Sliding_Window) plus Sudden_Motion_Change to compute a fall confidence score (0.0 to 1.0).
2. WHEN the Posture_Score exceeds 0.7 and the Cumulative_Delta shows a Center_Of_Gravity_Height drop greater than 0.15 within the Sliding_Window, THE Fall_Agent SHALL assign a fall confidence of at least 0.8.
3. WHEN the Posture_Score exceeds 0.7 but the Cumulative_Delta is near zero (person already on the ground with no recent motion), THE Fall_Agent SHALL assign a fall confidence of at least 0.5 after observing the collapsed posture for at least 1 second of frames.
4. WHEN the Cumulative_Delta shows a large Center_Of_Gravity_Height drop (greater than 0.2) but the Posture_Score is below 0.4 (person crouched but not collapsed), THE Fall_Agent SHALL assign a fall confidence below 0.4.
5. THE Fall_Agent SHALL remove the velocity gate (`if velocity < 0.02: return 0.0`) from the current implementation and replace it with the combined 5-feature approach.
6. WHEN a spike in Sudden_Motion_Change (feature 4) is followed within 1 second by a high Posture_Score (features 1–3), THE Fall_Agent SHALL boost the fall confidence by at least 0.1, as this pattern indicates an impact event.

### Requirement 4: Unconsciousness / Incapacitation Detection via Stillness Duration

**User Story:** As a fall detection system, I want to detect unconsciousness by combining Stillness_Duration (feature 5) with additional signals, so that I can distinguish between a person who fell and is incapacitated versus someone who is intentionally lying still.

#### Acceptance Criteria

1. WHEN the Fall_Agent transitions to MONITORING_RECOVERY state, THE Fall_Agent SHALL begin tracking Stillness_Duration (feature 5) and compute an Unconsciousness_Score (0.0 to 1.0) combining multiple signals.
2. THE Unconsciousness_Score SHALL incorporate four weighted signals: (a) Stillness_Duration — how long Sudden_Motion_Change has remained below the stillness threshold, (b) micro-movement absence — lack of small landmark jitter that conscious people exhibit (head adjustments, hand shifts, breathing motion), (c) posture abnormality — how unnatural the limb positions are (limb asymmetry, awkward joint angles a conscious person would not hold), and (d) fall-preceded context — whether the current state was reached via a rapid posture transition (spike in feature 4) rather than a gradual lie-down.
3. THE Feature_Extractor SHALL compute a micro-movement metric by measuring the standard deviation of landmark positions over a 3-to-5-second sub-window; a conscious person at rest typically produces a micro-movement value above 0.002 due to breathing and minor adjustments.
4. THE Feature_Extractor SHALL compute a posture abnormality metric by measuring limb symmetry (difference between left and right arm angles, left and right leg angles) and detecting joint angles outside normal resting ranges.
5. WHILE in MONITORING_RECOVERY state, IF the Unconsciousness_Score remains above 0.6 and the Posture_Score remains above 0.6 for the duration of the Recovery_Timer, THEN THE Fall_Agent SHALL transition to CRITICAL_ALERT state.
6. WHILE in MONITORING_RECOVERY state, WHEN the Posture_Score drops below 0.3 and the Center_Of_Gravity_Height decreases by more than 0.1 from its highest point (person rising), THE Fall_Agent SHALL transition to RECOVERED state.
7. WHILE in MONITORING_RECOVERY state, WHEN significant intentional motion is detected (Sudden_Motion_Change exceeds 0.02) but the Posture_Score remains above 0.5, THE Fall_Agent SHALL remain in MONITORING_RECOVERY state and continue the Recovery_Timer.
8. THE Fall_Agent SHALL weight the fall-preceded context signal such that a person who transitioned rapidly from upright to ground (Cumulative_Delta Center_Of_Gravity_Height drop > 0.15 within 2 seconds) receives a higher Unconsciousness_Score than a person who gradually lowered themselves to the ground.

### Requirement 5: State Machine Stability (Anti-Flicker)

**User Story:** As a fall detection system, I want the state machine to make stable transitions based on accumulated evidence rather than single-frame readings, so that the agent does not flicker between states.

#### Acceptance Criteria

1. THE Fall_Agent SHALL require a fall confidence above the configured threshold for at least 3 consecutive frames before transitioning from NORMAL to SUSPICIOUS_EVENT.
2. THE Fall_Agent SHALL require the fall confidence to drop below 50% of the configured threshold for at least 5 consecutive frames before transitioning from SUSPICIOUS_EVENT back to NORMAL.
3. WHEN transitioning from SUSPICIOUS_EVENT to MONITORING_RECOVERY, THE Fall_Agent SHALL require the fall confidence to remain above the threshold for at least 5 consecutive frames.
4. THE Fall_Agent SHALL use an exponential moving average of the fall confidence score across frames rather than the raw per-frame value, with a smoothing factor between 0.2 and 0.4.
5. IF a single frame produces a pose detection failure (no landmarks detected), THEN THE Fall_Agent SHALL hold its current state for up to 10 frames before reverting to NORMAL.

### Requirement 6: Video Input Pipeline

**User Story:** As a user, I want to provide video files (MP4, AVI, MOV) or a live webcam feed as input, so that the system can process real video footage frame-by-frame for fall detection.

#### Acceptance Criteria

1. THE Fall_Detector SHALL accept video files in MP4, AVI, MOV, MKV, WMV, and FLV formats as input.
2. THE Fall_Detector SHALL accept live webcam feeds identified by device index as input.
3. THE Fall_Detector SHALL accept folders of sequential images (JPEG, PNG) as input, treating them as video frame sequences.
4. WHEN processing a video file, THE Fall_Detector SHALL extract frames at the video's native frame rate and process each frame through the Pose_Estimator and Feature_Extractor.
5. WHEN processing a live webcam feed, THE Fall_Detector SHALL process frames in real-time at a target rate of 24 frames per second.
6. IF the video source cannot be opened, THEN THE Fall_Detector SHALL return a descriptive error message identifying the source path and the failure reason.

### Requirement 7: Pose Estimator Abstraction Layer

**User Story:** As a developer, I want the pose estimation to be behind an abstraction layer, so that MediaPipe can be swapped for another backend (e.g., for thermal/infrared footage) without changing the detection logic.

#### Acceptance Criteria

1. THE Pose_Estimator SHALL expose a consistent interface that accepts a BGR image frame and returns a list of detected persons, each with 33 landmark points containing x, y, z coordinates and a visibility score.
2. THE Fall_Detector logic (Feature_Extractor and Fall_Agent) SHALL depend only on the Pose_Estimator interface, not on MediaPipe-specific types or APIs.
3. THE default Pose_Estimator implementation SHALL use MediaPipe PoseLandmarker with the pose_landmarker_heavy model.
4. WHEN a Pose_Estimator implementation fails to detect any pose in a frame, THE Pose_Estimator SHALL return an empty list rather than raising an exception.

### Requirement 8: WebSocket Integration and Frontend Streaming

**User Story:** As a dashboard user, I want to see real-time fall detection results streamed to the frontend, so that I can monitor the system's state and receive alerts.

#### Acceptance Criteria

1. THE Fall_Detector SHALL stream annotated video frames, agent state, and feature data to connected WebSocket clients at a target rate of 24 frames per second.
2. WHEN the Fall_Agent transitions to CRITICAL_ALERT state, THE Fall_Detector SHALL send a WebSocket message of type "critical_alert" containing the alert details, event summary, and confidence score.
3. THE WebSocket message format SHALL remain compatible with the existing frontend WSMessage interface, including the frame (base64 JPEG), agent_state, features, pose_detected, and num_people fields.
4. WHEN the Fall_Agent state changes, THE Fall_Detector SHALL include the new state in the next WebSocket message sent to all connected clients.
5. THE Fall_Detector SHALL include the Posture_Score and Cumulative_Delta values in the features payload sent to the frontend, in addition to the existing feature fields.

### Requirement 9: Test Dataset Compatibility

**User Story:** As a developer, I want to run the fall detection system against the existing test datasets (laying PNGs, sample MP4 videos, and image sequence folders), so that I can validate detection accuracy.

#### Acceptance Criteria

1. WHEN processing the laying PNG dataset (24 static images of people lying down), THE Fall_Detector SHALL assign a Posture_Score above 0.6 for at least 20 of the 24 images.
2. WHEN processing the sample MP4 videos, THE Fall_Detector SHALL detect state transitions (not remain stuck in NORMAL for the entire video).
3. THE Fall_Detector SHALL be testable via the existing `test_dataset.py` command-line interface with the same argument format.
4. THE Fall_Detector SHALL produce a summary report showing per-source results including final state, maximum confidence, and number of state transitions.
5. WHEN processing a single static image (not a video sequence), THE Fall_Detector SHALL evaluate the Posture_Score from that single frame and report the result without requiring frame-to-frame history.

### Requirement 10: Configuration and Tuning

**User Story:** As a developer, I want to configure detection thresholds and window sizes, so that I can tune the system for different environments and camera setups.

#### Acceptance Criteria

1. THE Fall_Detector SHALL expose configurable parameters for: fall confidence threshold (default 0.55), recovery window duration in seconds (default 10.0), sliding window size in frames (default 20), and stillness threshold (default 0.005).
2. THE Fall_Detector SHALL accept configuration updates via the existing REST API endpoint (`POST /config`).
3. WHEN configuration is updated at runtime, THE Fall_Detector SHALL apply the new parameters to subsequent frames without requiring a restart.
4. THE Fall_Detector SHALL use the existing `AppConfig` Pydantic model extended with the new configuration fields.
5. IF a configuration value is outside its valid range, THEN THE Fall_Detector SHALL reject the update and return an error message specifying the valid range.
