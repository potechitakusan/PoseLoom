"""
img2BVH Main CLI Tool.
Extracts 3D pose landmarks from a 2D image and exports a Humanoid BVH file.
"""

import argparse
import os
import sys
import cv2
from pathlib import Path

# Add current dir to path
sys.path.append(str(Path(__file__).parent.resolve()))

from pose_estimator import PoseEstimator
from bvh_skeleton import BVHHumanoid


def process_single_image(image_path, output_bvh, output_viz=None, model_path="models/pose_landmarker_heavy.task"):
    print(f"[*] Processing image: {image_path}")
    estimator = PoseEstimator(model_path=model_path)
    joints_3d, annotated_image, results = estimator.process_image(image_path)

    if joints_3d is None:
        print(f"[!] Warning: No human pose detected in {image_path}")
        return False

    # Export BVH
    humanoid = BVHHumanoid(scale=100.0) # meters to cm
    bvh_content = humanoid.generate_bvh(joints_3d)

    os.makedirs(os.path.dirname(os.path.abspath(output_bvh)), exist_ok=True)
    with open(output_bvh, "w", encoding="utf-8") as f:
        f.write(bvh_content)
    print(f"[+] Saved BVH to: {output_bvh}")

    # Export visualization if requested
    if output_viz:
        os.makedirs(os.path.dirname(os.path.abspath(output_viz)), exist_ok=True)
        cv2.imwrite(output_viz, annotated_image)
        print(f"[+] Saved pose visualization to: {output_viz}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Convert 2D human pose image to 3D BVH file.")
    parser.add_argument("--input", "-i", required=True, help="Path to input image")
    parser.add_argument("--output_bvh", "-o", required=True, help="Path to output .bvh file")
    parser.add_argument("--output_viz", "-v", default=None, help="Path to output visualization .png file")
    parser.add_argument("--model", "-m", default="models/pose_landmarker_heavy.task", help="Path to pose landmarker model")

    args = parser.parse_args()
    success = process_single_image(
        image_path=args.input,
        output_bvh=args.output_bvh,
        output_viz=args.output_viz,
        model_path=args.model
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
