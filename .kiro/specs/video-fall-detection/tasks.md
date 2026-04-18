# Implementation Plan: Video Fall Detection — 5-Feature Rewrite

## Overview

Rewrite the SentinelCare fall detection pipeline to replace the velocity-gated approach with a 5-core-feature system that computes Body Axis Angle, Center of Gravity Height, Aspect Ratio, Sudden Motion Change, and Stillness Duration from pose landmarks. The new system detects falls from both video streams and static images by combining a single-frame Posture Score with frame-to-frame Cumulative Delta analysis, using EMA smoothing and consecutive-frame gating for stable state transitions.

Tasks are ordered so the user can test fall detection on MP4 datasets as early as possible.

## Tasks

- [x] 1. Extend data models with new feature fields
  - [x] 1.1 Add new fields to `FrameFeatures` (rename from `PoseFeatures`) in `app/models.py`
    - Add `body_axis_angle: float` (degrees from vertical, replaces `torso_angle`)
    - Add `center_of_gravity_height: float` (replaces `body_centroid_y`)
    - Add `aspect_ratio: float` (bounding box height / width)
    - Add `sudden_motion_change: float` (replaces `motion_energy`)
    - Add `stillness_duration: float` (consecutive seconds below stillness threshold)
    - Add `posture_score: float` (composite 0.0–1.0)
    - Add `cumulative_delta_angle: float`
    - Add `cumulative_delta_cog: float`
    - Add `cumulative_delta_aspect: float`
    - Keep existing fields as aliases for backward compatibility with frontend
    - _Requirements: 1.1, 2.1, 2.2, 8.3, 8.5_

  - [x] 1.2 Extend `AppConfig` in `app/models.py` with new configuration fields
    - Add `sliding_window_size: int = 20` (frames)
    - Add `stillness_threshold: float = 0.005`
    - Add validation that rejects out-of-range values
    - _Requirements: 10.1, 10.4, 10.5_

- [x] 2. Rewrite `features.py` — 5 core features + Posture Score + Cumulative Delta
  - [x] 2.1 Implement the 5 core feature computations in `FeatureExtractor`
    - Compute **Body Axis Angle**: angle of shoulder-midpoint → hip-midpoint vector vs vertical (0°=upright, 90°=horizontal)
    - Compute **Center of Gravity Height**: average Y of shoulders, hips, knees
    - Compute **Aspect Ratio**: bounding box height ÷ width from all visible landmarks (min/max x, y)
    - Compute **Sudden Motion Change**: sum of Euclidean distances between each landmark's current and previous position
    - Compute **Stillness Duration**: consecutive seconds where Sudden Motion Change < stillness threshold, using frame rate to convert frames to seconds
    - Maintain a `Sliding_Window` (deque) of the most recent N frames of landmark data and computed features
    - When window has fewer frames than configured size, compute deltas using all available frames
    - When no pose is detected, retain last known landmarks and mark frame as detection gap
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7_

  - [x] 2.2 Implement Posture Score computation (velocity-independent)
    - Weighted combination of Body Axis Angle, Center of Gravity Height, and Aspect Ratio
    - When Body Axis Angle > 55° and CoG Height > 0.6 → Posture Score ≥ 0.7
    - When Body Axis Angle < 15° (upright) → Posture Score < 0.2
    - When Aspect Ratio < 1.0 (wider than tall) → boost Posture Score by ≥ 0.15
    - Must be computable from a single frame with no history
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.3 Implement Cumulative Delta computation
    - Compare current frame features to oldest frame in Sliding Window
    - Compute delta for Body Axis Angle, Center of Gravity Height, and Aspect Ratio
    - Store deltas in the returned `FrameFeatures` object
    - _Requirements: 1.4, 3.1_

  - [ ]* 2.4 Write property tests for Posture Score boundaries
    - **Property 1: Collapsed posture produces high score** — When Body Axis Angle > 55° AND CoG Height > 0.6, Posture Score ≥ 0.7
    - **Validates: Requirements 2.3**
    - **Property 2: Upright posture produces low score** — When Body Axis Angle < 15°, Posture Score < 0.2
    - **Validates: Requirements 2.4**
    - **Property 3: Low aspect ratio boosts score** — When Aspect Ratio < 1.0, Posture Score increases by ≥ 0.15 compared to same pose with Aspect Ratio > 1.5
    - **Validates: Requirements 2.5**

  - [ ]* 2.5 Write unit tests for feature extraction
    - Test Body Axis Angle computation with known landmark positions (upright, horizontal, 45°)
    - Test Aspect Ratio computation with known bounding boxes
    - Test Stillness Duration accumulation and reset
    - Test Sliding Window behavior when partially filled
    - Test detection gap handling (no pose detected)
    - _Requirements: 1.1, 1.3, 1.6, 1.7_

- [x] 3. Rewrite `agent.py` — combined scoring with EMA and consecutive-frame gating
  - [x] 3.1 Implement new `_compute_fall_confidence` using combined 5-feature approach
    - Remove the velocity gate (`if velocity < 0.02: return 0.0`)
    - Use weighted combination of Posture Score and Cumulative Delta plus Sudden Motion Change
    - When Posture Score > 0.7 AND CoG delta drop > 0.15 → confidence ≥ 0.8
    - When Posture Score > 0.7 AND Cumulative Delta ≈ 0 (already on ground, no recent motion) → confidence ≥ 0.5 after 1 second of collapsed posture
    - When CoG delta drop > 0.2 but Posture Score < 0.4 (crouching) → confidence < 0.4
    - When Sudden Motion Change spike followed within 1s by high Posture Score → boost confidence by ≥ 0.1
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 3.2 Implement EMA smoothing and consecutive-frame gating for state transitions
    - Apply exponential moving average (α = 0.2–0.4) to fall confidence across frames
    - NORMAL → SUSPICIOUS_EVENT: require confidence above threshold for ≥ 3 consecutive frames
    - SUSPICIOUS_EVENT → NORMAL: require confidence below 50% of threshold for ≥ 5 consecutive frames
    - SUSPICIOUS_EVENT → MONITORING_RECOVERY: require confidence above threshold for ≥ 5 consecutive frames
    - On pose detection failure: hold current state for up to 10 frames before reverting
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 3.3 Update recovery and critical alert logic
    - In MONITORING_RECOVERY: track Stillness Duration, compute recovery based on Posture Score dropping below 0.3 and CoG Height decreasing by > 0.1
    - Transition to CRITICAL_ALERT when Posture Score remains > 0.6 for full Recovery Timer duration
    - Transition to RECOVERED when significant upright motion detected
    - _Requirements: 4.5, 4.6, 4.7_

  - [ ]* 3.4 Write property tests for fall confidence scoring
    - **Property 4: Collapsed posture with rapid drop yields high confidence** — Posture Score > 0.7 AND CoG delta > 0.15 → confidence ≥ 0.8
    - **Validates: Requirements 3.2**
    - **Property 5: Already-fallen static posture yields moderate confidence** — Posture Score > 0.7 AND Cumulative Delta ≈ 0 → confidence ≥ 0.5
    - **Validates: Requirements 3.3**
    - **Property 6: Crouching without collapse yields low confidence** — CoG delta > 0.2 AND Posture Score < 0.4 → confidence < 0.4
    - **Validates: Requirements 3.4**

  - [ ]* 3.5 Write unit tests for state machine transitions
    - Test NORMAL → SUSPICIOUS requires 3 consecutive high-confidence frames
    - Test SUSPICIOUS → NORMAL requires 5 consecutive low-confidence frames
    - Test EMA smoothing dampens single-frame spikes
    - Test pose detection failure holds state for up to 10 frames
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 4. Checkpoint — Core detection pipeline
  - Ensure all tests pass, ask the user if questions arise.
  - At this point, `features.py` and `agent.py` should be fully rewritten with the 5-feature approach.

- [x] 5. Update `test_dataset.py` to work with new feature API
  - [x] 5.1 Update `test_dataset.py` imports and feature extraction calls
    - Update import of `PoseFeatures` to `FrameFeatures` (or handle alias)
    - Update `FeatureExtractor` usage to pass frame rate info for Stillness Duration computation
    - Update `FallGuardAgent` construction to pass new config fields (sliding_window_size, stillness_threshold)
    - Display new feature values in `--show` overlay (Posture Score, Body Axis Angle, Aspect Ratio)
    - Ensure `python test_dataset.py datasets/` runs end-to-end with the new pipeline
    - _Requirements: 9.2, 9.3, 9.4_

  - [x] 5.2 Add single-image Posture Score evaluation mode
    - When a single static image is provided (not a video or sequence), compute Posture Score from that one frame and report result
    - No frame-to-frame history required for single images
    - _Requirements: 9.5, 2.6_

  - [ ]* 5.3 Write integration test for dataset processing
    - Test that laying PNG dataset produces Posture Score > 0.6 for at least 20 of 24 images
    - Test that sample MP4 videos produce state transitions (not stuck in NORMAL)
    - _Requirements: 9.1, 9.2_

- [x] 6. Checkpoint — Dataset testing works
  - Ensure all tests pass, ask the user if questions arise.
  - User should be able to run `python test_dataset.py datasets/` and see fall detection results on their MP4 files.

- [ ] 7. Add PoseEstimator abstraction to `vision.py`
  - [ ] 7.1 Create `PoseEstimator` abstract base class and `MediaPipePoseEstimator` implementation
    - Define abstract interface: `estimate(frame: np.ndarray) -> list[PoseData]`
    - Accept BGR image, return list of detected persons with 33 landmarks each
    - Return empty list (not exception) when no pose detected
    - Move MediaPipe-specific code from `PoseTracker` into `MediaPipePoseEstimator`
    - Keep `PoseTracker` as a convenience wrapper that uses `PoseEstimator` internally
    - Ensure `FeatureExtractor` and `FallGuardAgent` depend only on the abstract interface types (`PoseData`, `LandmarkPoint`), not MediaPipe types
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 8. Update `main.py` WebSocket integration
  - [ ] 8.1 Wire new feature pipeline into the WebSocket vision loop
    - Update `_vision_loop` to use new `FeatureExtractor` API (pass frame rate, use new feature fields)
    - Update `FallGuardAgent` construction with new config fields from `AppConfig`
    - Include `posture_score` and cumulative delta values in the `WSMessage.features` payload
    - Ensure `WSMessage` format remains compatible with existing frontend
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 8.2 Update REST config endpoint to handle new fields
    - Ensure `POST /config` accepts and validates new `AppConfig` fields (sliding_window_size, stillness_threshold)
    - Apply new parameters to subsequent frames without restart
    - _Requirements: 10.2, 10.3_

- [ ] 9. Implement unconsciousness detection signals
  - [ ] 9.1 Add micro-movement metric to `FeatureExtractor`
    - Compute standard deviation of landmark positions over a 3–5 second sub-window
    - Conscious person at rest typically produces micro-movement > 0.002
    - _Requirements: 4.3_

  - [ ] 9.2 Add posture abnormality metric to `FeatureExtractor`
    - Measure limb symmetry (left vs right arm angles, left vs right leg angles)
    - Detect joint angles outside normal resting ranges
    - _Requirements: 4.4_

  - [ ] 9.3 Implement Unconsciousness Score in `FallGuardAgent`
    - Combine four weighted signals: Stillness Duration, micro-movement absence, posture abnormality, fall-preceded context
    - Weight fall-preceded context higher when rapid transition detected (CoG delta > 0.15 within 2 seconds)
    - Use Unconsciousness Score (> 0.6) combined with Posture Score (> 0.6) for CRITICAL_ALERT transition
    - _Requirements: 4.1, 4.2, 4.5, 4.8_

  - [ ]* 9.4 Write unit tests for unconsciousness detection
    - Test micro-movement metric with synthetic landmark jitter
    - Test posture abnormality with symmetric vs asymmetric poses
    - Test Unconsciousness Score weighting with fall-preceded vs gradual lie-down
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.8_

- [ ] 10. Final checkpoint — Full pipeline validation
  - Ensure all tests pass, ask the user if questions arise.
  - Verify `python test_dataset.py datasets/` detects falls in MP4 videos and scores laying PNGs correctly.
  - Verify WebSocket streaming works with `uvicorn app.main:app`.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Tasks 1–6 are prioritized so the user can test MP4 fall detection on their local machine ASAP
- Tasks 7–9 add abstraction and advanced detection features after core pipeline works
- The existing Python codebase (Python 3.10, MediaPipe, OpenCV, FastAPI) is preserved — no new dependencies needed
- Property tests validate universal correctness properties from the design
- Unit tests validate specific examples and edge cases
