"""
Pose Estimator using MediaPipe 1.0 Tasks API for 3D landmarks extraction.
Outputs world coordinates (x, y, z in meters) and 2D overlay preview.
"""

import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Landmark connectivity for skeleton drawing
POSE_CONNECTIONS = [
    (11, 12), # shoulders
    (11, 13), (13, 15), # left arm
    (12, 14), (14, 16), # right arm
    (11, 23), (12, 24), # torso
    (23, 24), # hips
    (23, 25), (25, 27), (27, 31), # left leg
    (24, 26), (26, 28), (28, 32), # right leg
    (0, 11), (0, 12), # head to shoulders
]


class PoseEstimator:
    def __init__(self, model_path="models/pose_landmarker_heavy.task", min_detection_confidence=0.5):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Pose Landmarker model not found at {model_path}")
            
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            output_segmentation_masks=False,
            num_poses=1,
            min_pose_detection_confidence=min_detection_confidence,
            min_pose_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_detection_confidence
        )
        self.detector = vision.PoseLandmarker.create_from_options(options)

    def process_image(self, image_path):
        """
        Processes image and returns (joints_3d, annotated_image, results).
        joints_3d is a dict of named 3D coordinates.
        """
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Could not load image at {image_path}")

        mp_image = mp.Image.create_from_file(image_path)
        results = self.detector.detect(mp_image)

        if not results.pose_world_landmarks or len(results.pose_world_landmarks) == 0:
            return None, image, None

        # Extract 33 world landmarks (x, y, z in meters, origin near hips)
        wl = results.pose_world_landmarks[0]
        
        # Helper to get numpy point
        def p(idx):
            lm = wl[idx]
            return np.array([lm.x, lm.y, lm.z])

        # MediaPipe landmark indices
        l_hip = p(23)
        r_hip = p(24)
        l_shldr = p(11)
        r_shldr = p(12)
        
        hips = (l_hip + r_hip) * 0.5
        chest = (l_shldr + r_shldr) * 0.5
        spine = hips + (chest - hips) * 0.5
        nose = p(0)
        neck = chest + (nose - chest) * 0.4
        head = nose

        joints_3d = {
            "Hips": hips,
            "Spine": spine,
            "Chest": chest,
            "Neck": neck,
            "Head": head,
            
            "LeftShoulder": l_shldr,
            "LeftArm": p(13),        # Left Elbow
            "LeftForeArm": p(15),    # Left Wrist
            "LeftHand": p(19),       # Left Index
            
            "RightShoulder": r_shldr,
            "RightArm": p(14),       # Right Elbow
            "RightForeArm": p(16),   # Right Wrist
            "RightHand": p(20),      # Right Index
            
            "LeftUpLeg": l_hip,
            "LeftLeg": p(25),        # Left Knee
            "LeftFoot": p(27),       # Left Ankle
            "LeftToe": p(31),        # Left Toe
            
            "RightUpLeg": r_hip,
            "RightLeg": p(26),       # Right Knee
            "RightFoot": p(28),      # Right Ankle
            "RightToe": p(32),       # Right Toe
        }

        # Create annotated image with 2D landmarks overlay
        annotated_image = image.copy()
        if results.pose_landmarks and len(results.pose_landmarks) > 0:
            lms_2d = results.pose_landmarks[0]
            h, w, _ = image.shape
            
            # Draw connections
            for p1_idx, p2_idx in POSE_CONNECTIONS:
                p1 = lms_2d[p1_idx]
                p2 = lms_2d[p2_idx]
                x1, y1 = int(p1.x * w), int(p1.y * h)
                x2, y2 = int(p2.x * w), int(p2.y * h)
                cv2.line(annotated_image, (x1, y1), (x2, y2), (0, 255, 0), 3)

            # Draw joints
            for lm in lms_2d:
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(annotated_image, (cx, cy), 5, (0, 0, 255), -1)

        return joints_3d, annotated_image, results
