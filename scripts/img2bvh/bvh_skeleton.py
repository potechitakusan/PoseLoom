"""
BVH Skeleton Definition and Exporter for img2BVH.
Standard Humanoid hierarchy compatible with Blender, Unity, and Mixamo.
"""

import numpy as np
from scipy.spatial.transform import Rotation as R

# Standard T-Pose bone rest directions (normalized)
REST_DIRECTIONS = {
    "Spine": np.array([0.0, 1.0, 0.0]),
    "Chest": np.array([0.0, 1.0, 0.0]),
    "Neck": np.array([0.0, 1.0, 0.0]),
    "Head": np.array([0.0, 1.0, 0.0]),
    
    "LeftShoulder": np.array([1.0, 0.2, 0.0]) / np.linalg.norm([1.0, 0.2, 0.0]),
    "LeftArm": np.array([1.0, 0.0, 0.0]),
    "LeftForeArm": np.array([1.0, 0.0, 0.0]),
    "LeftHand": np.array([1.0, 0.0, 0.0]),
    
    "RightShoulder": np.array([-1.0, 0.2, 0.0]) / np.linalg.norm([-1.0, 0.2, 0.0]),
    "RightArm": np.array([-1.0, 0.0, 0.0]),
    "RightForeArm": np.array([-1.0, 0.0, 0.0]),
    "RightHand": np.array([-1.0, 0.0, 0.0]),
    
    "LeftUpLeg": np.array([0.0, -1.0, 0.0]),
    "LeftLeg": np.array([0.0, -1.0, 0.0]),
    "LeftFoot": np.array([0.0, -0.2, 0.8]) / np.linalg.norm([0.0, -0.2, 0.8]),
    
    "RightUpLeg": np.array([0.0, -1.0, 0.0]),
    "RightLeg": np.array([0.0, -1.0, 0.0]),
    "RightFoot": np.array([0.0, -0.2, 0.8]) / np.linalg.norm([0.0, -0.2, 0.8]),
}

def rotation_between_vectors(v_from, v_to):
    """Compute rotation quaternion from v_from to v_to."""
    v_from = v_from / (np.linalg.norm(v_from) + 1e-8)
    v_to = v_to / (np.linalg.norm(v_to) + 1e-8)
    
    dot = np.dot(v_from, v_to)
    if dot > 0.999999:
        return R.identity()
    elif dot < -0.999999:
        # 180 degree rotation around arbitrary orthogonal axis
        axis = np.cross(v_from, np.array([1.0, 0.0, 0.0]))
        if np.linalg.norm(axis) < 1e-4:
            axis = np.cross(v_from, np.array([0.0, 1.0, 0.0]))
        axis = axis / np.linalg.norm(axis)
        return R.from_rotvec(np.pi * axis)
    
    axis = np.cross(v_from, v_to)
    axis_norm = np.linalg.norm(axis)
    axis = axis / (axis_norm + 1e-8)
    angle = np.arccos(np.clip(dot, -1.0, 1.0))
    return R.from_rotvec(angle * axis)


class BVHHumanoid:
    """Manages Humanoid skeleton hierarchy and converts estimated 3D joints to BVH."""

    def __init__(self, scale=100.0):
        # Scale: MediaPipe output is in meters, standard BVH often uses cm (scale=100)
        self.scale = scale

    def generate_bvh(self, joints_3d):
        """
        joints_3d: dictionary mapping joint names to (x, y, z) numpy arrays in camera space.
        Coordinate system convention:
          MediaPipe: X right, Y down, Z forward (depth away from camera)
          BVH / Blender: X right, Y up, Z forward (depth towards viewer / Y up)
          We convert MediaPipe (x, y, z) -> BVH (x, -y, -z)
        """
        # Convert coordinates to BVH space (Y-up, Z-forward)
        pts = {}
        for k, v in joints_3d.items():
            pts[k] = np.array([v[0], -v[1], -v[2]]) * self.scale

        # Compute bone vectors
        bone_vecs = {
            "Spine": pts["Chest"] - pts["Hips"],
            "Chest": pts["Neck"] - pts["Chest"],
            "Neck": pts["Head"] - pts["Neck"],
            "LeftShoulder": pts["LeftArm"] - pts["Chest"],
            "LeftArm": pts["LeftForeArm"] - pts["LeftArm"],
            "LeftForeArm": pts["LeftHand"] - pts["LeftForeArm"],
            "RightShoulder": pts["RightArm"] - pts["Chest"],
            "RightArm": pts["RightForeArm"] - pts["RightArm"],
            "RightForeArm": pts["RightHand"] - pts["RightForeArm"],
            "LeftUpLeg": pts["LeftLeg"] - pts["LeftUpLeg"],
            "LeftLeg": pts["LeftFoot"] - pts["LeftLeg"],
            "LeftFoot": pts["LeftToe"] - pts["LeftFoot"] if "LeftToe" in pts else np.array([0, -2, 10]),
            "RightUpLeg": pts["RightLeg"] - pts["RightUpLeg"],
            "RightLeg": pts["RightFoot"] - pts["RightLeg"],
            "RightFoot": pts["RightToe"] - pts["RightToe"] if "RightToe" in pts else np.array([0, -2, 10]),
        }

        # Calculate rotations (Global then Local)
        # Root (Hips) orientation: based on hip-to-hip line and spine line
        hip_vec = pts["LeftUpLeg"] - pts["RightUpLeg"]
        spine_vec = pts["Chest"] - pts["Hips"]
        normal_vec = np.cross(hip_vec, spine_vec)
        
        # Calculate bone rotations with hierarchical compensation
        rotations = {}
        global_rot = {}

        # 1. Hips (Root)
        global_rot["Hips"] = R.identity()
        rotations["Hips"] = np.array([0.0, 0.0, 0.0]) # Euler angles in ZXY

        # Hierarchy processing order: (Bone, Parent)
        hierarchy_order = [
            ("Spine", "Hips"),
            ("Chest", "Spine"),
            ("Neck", "Chest"),
            ("Head", "Neck"),
            ("LeftShoulder", "Chest"),
            ("LeftArm", "LeftShoulder"),
            ("LeftForeArm", "LeftArm"),
            ("LeftHand", "LeftForeArm"),
            ("RightShoulder", "Chest"),
            ("RightArm", "RightShoulder"),
            ("RightForeArm", "RightArm"),
            ("RightHand", "RightForeArm"),
            ("LeftUpLeg", "Hips"),
            ("LeftLeg", "LeftUpLeg"),
            ("LeftFoot", "LeftLeg"),
            ("RightUpLeg", "Hips"),
            ("RightLeg", "RightUpLeg"),
            ("RightFoot", "RightLeg"),
        ]

        for bone, parent in hierarchy_order:
            if bone in bone_vecs and bone in REST_DIRECTIONS:
                target_vec = bone_vecs[bone]
                rest_vec = REST_DIRECTIONS[bone]
                g_rot = rotation_between_vectors(rest_vec, target_vec)
                global_rot[bone] = g_rot
                
                # Local rotation = parent_global_inv * current_global
                parent_g_rot = global_rot.get(parent, R.identity())
                l_rot = parent_g_rot.inv() * g_rot
                rotations[bone] = l_rot.as_euler("ZXY", degrees=True)
            else:
                rotations[bone] = np.array([0.0, 0.0, 0.0])
                global_rot[bone] = global_rot.get(parent, R.identity())

        # Build BVH String
        bvh_text = self._build_bvh_text(pts, rotations)
        return bvh_text

    def _build_bvh_text(self, pts, rotations):
        # T-Pose Default Offsets
        root_pos = pts["Hips"]
        
        # Calculate actual lengths or standard proportions
        chest_off = pts["Chest"] - pts["Hips"]
        neck_off = pts["Neck"] - pts["Chest"]
        head_off = pts["Head"] - pts["Neck"]
        
        l_shldr_off = pts["LeftShoulder"] - pts["Chest"]
        l_arm_off = pts["LeftArm"] - pts["LeftShoulder"]
        l_forearm_off = pts["LeftForeArm"] - pts["LeftArm"]
        l_hand_off = pts["LeftHand"] - pts["LeftForeArm"]
        
        r_shldr_off = pts["RightShoulder"] - pts["Chest"]
        r_arm_off = pts["RightArm"] - pts["RightShoulder"]
        r_forearm_off = pts["RightForeArm"] - pts["RightArm"]
        r_hand_off = pts["RightHand"] - pts["RightForeArm"]
        
        l_upleg_off = pts["LeftUpLeg"] - pts["Hips"]
        l_leg_off = pts["LeftLeg"] - pts["LeftUpLeg"]
        l_foot_off = pts["LeftFoot"] - pts["LeftLeg"]
        
        r_upleg_off = pts["RightUpLeg"] - pts["Hips"]
        r_leg_off = pts["RightLeg"] - pts["RightUpLeg"]
        r_foot_off = pts["RightFoot"] - pts["RightLeg"]

        lines = []
        lines.append("HIERARCHY")
        lines.append("ROOT Hips")
        lines.append("{")
        lines.append(f"\tOFFSET 0.000000 {root_pos[1]:.6f} {root_pos[2]:.6f}")
        lines.append("\tCHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation")
        
        # Chest / Spine
        lines.append("\tJOINT Spine")
        lines.append("\t{")
        lines.append(f"\t\tOFFSET {chest_off[0]*0.5:.6f} {chest_off[1]*0.5:.6f} {chest_off[2]*0.5:.6f}")
        lines.append("\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\tJOINT Chest")
        lines.append("\t\t{")
        lines.append(f"\t\t\tOFFSET {chest_off[0]*0.5:.6f} {chest_off[1]*0.5:.6f} {chest_off[2]*0.5:.6f}")
        lines.append("\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        
        # Neck & Head
        lines.append("\t\t\tJOINT Neck")
        lines.append("\t\t\t{")
        lines.append(f"\t\t\t\tOFFSET {neck_off[0]:.6f} {neck_off[1]:.6f} {neck_off[2]:.6f}")
        lines.append("\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\tJOINT Head")
        lines.append("\t\t\t\t{")
        lines.append(f"\t\t\t\t\tOFFSET {head_off[0]:.6f} {head_off[1]:.6f} {head_off[2]:.6f}")
        lines.append("\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\t\tEnd Site")
        lines.append("\t\t\t\t\t{")
        lines.append("\t\t\t\t\t\tOFFSET 0.000000 10.000000 0.000000")
        lines.append("\t\t\t\t\t}")
        lines.append("\t\t\t\t}")
        lines.append("\t\t\t}")
        
        # Left Arm Chain
        lines.append("\t\t\tJOINT LeftShoulder")
        lines.append("\t\t\t{")
        lines.append(f"\t\t\t\tOFFSET {l_shldr_off[0]:.6f} {l_shldr_off[1]:.6f} {l_shldr_off[2]:.6f}")
        lines.append("\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\tJOINT LeftArm")
        lines.append("\t\t\t\t{")
        lines.append(f"\t\t\t\t\tOFFSET {l_arm_off[0]:.6f} {l_arm_off[1]:.6f} {l_arm_off[2]:.6f}")
        lines.append("\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\t\tJOINT LeftForeArm")
        lines.append("\t\t\t\t\t{")
        lines.append(f"\t\t\t\t\t\tOFFSET {l_forearm_off[0]:.6f} {l_forearm_off[1]:.6f} {l_forearm_off[2]:.6f}")
        lines.append("\t\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\t\t\tJOINT LeftHand")
        lines.append("\t\t\t\t\t\t{")
        lines.append(f"\t\t\t\t\t\t\tOFFSET {l_hand_off[0]:.6f} {l_hand_off[1]:.6f} {l_hand_off[2]:.6f}")
        lines.append("\t\t\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\t\t\t\tEnd Site")
        lines.append("\t\t\t\t\t\t\t{")
        lines.append("\t\t\t\t\t\t\t\tOFFSET 8.000000 0.000000 0.000000")
        lines.append("\t\t\t\t\t\t\t}")
        lines.append("\t\t\t\t\t\t}")
        lines.append("\t\t\t\t\t}")
        lines.append("\t\t\t\t}")
        lines.append("\t\t\t}")
        
        # Right Arm Chain
        lines.append("\t\t\tJOINT RightShoulder")
        lines.append("\t\t\t{")
        lines.append(f"\t\t\t\tOFFSET {r_shldr_off[0]:.6f} {r_shldr_off[1]:.6f} {r_shldr_off[2]:.6f}")
        lines.append("\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\tJOINT RightArm")
        lines.append("\t\t\t\t{")
        lines.append(f"\t\t\t\t\tOFFSET {r_arm_off[0]:.6f} {r_arm_off[1]:.6f} {r_arm_off[2]:.6f}")
        lines.append("\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\t\tJOINT RightForeArm")
        lines.append("\t\t\t\t\t{")
        lines.append(f"\t\t\t\t\t\tOFFSET {r_forearm_off[0]:.6f} {r_forearm_off[1]:.6f} {r_forearm_off[2]:.6f}")
        lines.append("\t\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\t\t\tJOINT RightHand")
        lines.append("\t\t\t\t\t\t{")
        lines.append(f"\t\t\t\t\t\t\tOFFSET {r_hand_off[0]:.6f} {r_hand_off[1]:.6f} {r_hand_off[2]:.6f}")
        lines.append("\t\t\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\t\t\t\tEnd Site")
        lines.append("\t\t\t\t\t\t\t{")
        lines.append("\t\t\t\t\t\t\t\tOFFSET -8.000000 0.000000 0.000000")
        lines.append("\t\t\t\t\t\t\t}")
        lines.append("\t\t\t\t\t\t}")
        lines.append("\t\t\t\t\t}")
        lines.append("\t\t\t\t}")
        lines.append("\t\t\t}")
        lines.append("\t\t}")
        lines.append("\t}")
        
        # Left Leg Chain
        lines.append("\tJOINT LeftUpLeg")
        lines.append("\t{")
        lines.append(f"\t\tOFFSET {l_upleg_off[0]:.6f} {l_upleg_off[1]:.6f} {l_upleg_off[2]:.6f}")
        lines.append("\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\tJOINT LeftLeg")
        lines.append("\t\t{")
        lines.append(f"\t\t\tOFFSET {l_leg_off[0]:.6f} {l_leg_off[1]:.6f} {l_leg_off[2]:.6f}")
        lines.append("\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\tJOINT LeftFoot")
        lines.append("\t\t\t{")
        lines.append(f"\t\t\t\tOFFSET {l_foot_off[0]:.6f} {l_foot_off[1]:.6f} {l_foot_off[2]:.6f}")
        lines.append("\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\tEnd Site")
        lines.append("\t\t\t\t{")
        lines.append("\t\t\t\t\tOFFSET 0.000000 -5.000000 12.000000")
        lines.append("\t\t\t\t}")
        lines.append("\t\t\t}")
        lines.append("\t\t}")
        lines.append("\t}")
        
        # Right Leg Chain
        lines.append("\tJOINT RightUpLeg")
        lines.append("\t{")
        lines.append(f"\t\tOFFSET {r_upleg_off[0]:.6f} {r_upleg_off[1]:.6f} {r_upleg_off[2]:.6f}")
        lines.append("\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\tJOINT RightLeg")
        lines.append("\t\t{")
        lines.append(f"\t\t\tOFFSET {r_leg_off[0]:.6f} {r_leg_off[1]:.6f} {r_leg_off[2]:.6f}")
        lines.append("\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\tJOINT RightFoot")
        lines.append("\t\t\t{")
        lines.append(f"\t\t\t\tOFFSET {r_foot_off[0]:.6f} {r_foot_off[1]:.6f} {r_foot_off[2]:.6f}")
        lines.append("\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append("\t\t\t\tEnd Site")
        lines.append("\t\t\t\t{")
        lines.append("\t\t\t\t\tOFFSET 0.000000 -5.000000 12.000000")
        lines.append("\t\t\t\t}")
        lines.append("\t\t\t}")
        lines.append("\t\t}")
        lines.append("\t}")
        
        lines.append("}") # End ROOT Hips
        
        # MOTION section
        lines.append("MOTION")
        lines.append("Frames: 1")
        lines.append("Frame Time: 0.033333")
        
        # Flatten values in tree traversal order
        motion_order = [
            ("Hips", True), # Include pos + rot
            ("Spine", False),
            ("Chest", False),
            ("Neck", False),
            ("Head", False),
            ("LeftShoulder", False),
            ("LeftArm", False),
            ("LeftForeArm", False),
            ("LeftHand", False),
            ("RightShoulder", False),
            ("RightArm", False),
            ("RightForeArm", False),
            ("RightHand", False),
            ("LeftUpLeg", False),
            ("LeftLeg", False),
            ("LeftFoot", False),
            ("RightUpLeg", False),
            ("RightLeg", False),
            ("RightFoot", False),
        ]
        
        motion_vals = []
        for bone, is_root in motion_order:
            rot = rotations.get(bone, np.array([0.0, 0.0, 0.0]))
            if is_root:
                motion_vals.extend([f"{root_pos[0]:.4f}", f"{root_pos[1]:.4f}", f"{root_pos[2]:.4f}"])
            motion_vals.extend([f"{rot[0]:.4f}", f"{rot[1]:.4f}", f"{rot[2]:.4f}"])
            
        lines.append(" ".join(motion_vals))
        return "\n".join(lines)
