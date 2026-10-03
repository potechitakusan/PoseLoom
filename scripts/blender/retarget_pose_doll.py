"""Transfer a SAM3D FBX pose to a matching, editable IK pose doll.

The source FBX must use the same body preset as the base doll, or its recorded
reference preset for a rest-shaped anime variant. Native rest
transforms carry axial rotations that cannot be recovered from a posed BVH.
All IK/copy-rotation constraints, color drivers and stock presets are retained.
"""
import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0,str(Path(__file__).parent))
from rig_utils import activate
from pose_doll_tools import export_pose


def depth(bone):
    return 0 if bone.parent is None else depth(bone.parent)+1


def mesh_positions(mesh):
    evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data=evaluated.to_mesh()
    vertices=[mesh.matrix_world @ v.co for v in data.vertices]
    evaluated.to_mesh_clear()
    return vertices


def fit_pole(arm, side, middle, first, end, label, expected):
    """Match the inferred bend direction without changing preset pole angles."""
    start=expected[side+first].translation
    joint=expected[side+middle].translation
    tip=expected[side+end].translation
    axis=(tip-start).normalized()
    center=start+axis*(joint-start).dot(axis)
    radial=joint-center
    if radial.length<1e-5:
        radial=expected[side+first].to_3x3().col[0]
        radial-=axis*radial.dot(axis)
    radial.normalize()
    pole=arm.pose.bones[f'CTRL_{label}_{side}']
    base=pole.matrix.copy()
    radius=max(.35, (joint-center).length+.30)
    def trial(angle):
        point=center+(Quaternion(axis,angle)@radial)*radius
        matrix=base.copy()
        matrix.translation=point
        pole.matrix=matrix
        bpy.context.view_layer.update()
        return (arm.pose.bones[side+middle].head-joint).length
    best=min((trial(i*math.tau/48),i*math.tau/48) for i in range(48))
    angle=best[1]
    step=math.tau/48
    for _ in range(5):
        error,angle=min((trial(angle+step*i/4),angle+step*i/4) for i in range(-4,5))
        step/=4
    error=trial(angle)
    return error


def transfer(base_path,source_path,output_path,render_path=None,pose_json=None, *,
             pose_id=None,pose_label=None,portable_output=False):
    base_path,source_path,output_path=map(lambda x:Path(x).resolve(),(base_path,source_path,output_path))
    if output_path in (base_path,source_path):raise ValueError('Save the transferred pose to a new file')
    if source_path.suffix.lower()!='.fbx':raise ValueError('Use SAM3D --export-fbx with the doll body preset')
    base_hash=hashlib.sha256(base_path.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(base_path))
    arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE' and o.get('rig_version'))
    mesh=next(o for o in bpy.context.scene.objects if o.type=='MESH' and o.parent==arm)
    activate(arm)
    if arm.animation_data:arm.animation_data.action=None
    for pb in arm.pose.bones:pb.matrix_basis.identity()
    constraints=[(c,c.mute) for pb in arm.pose.bones for c in pb.constraints]
    for c,_ in constraints:c.mute=True
    existing=set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(source_path),use_anim=True)
    imported=set(bpy.context.scene.objects)-existing
    source=next(o for o in imported if o.type=='ARMATURE')
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    names=[b.name for b in sorted(arm.data.bones,key=depth) if b.name in source.pose.bones and not b.name.startswith('CTRL_')]
    needed={'Hips','Spine','Spine1','Spine2','Neck','Head'}|{s+p for s in ('Left','Right') for p in ('Arm','ForeArm','Hand','UpLeg','Leg','Foot')}
    if not needed.issubset(names):raise ValueError(f'Missing source bones: {needed-set(names)}')
    # Compare the native (or recorded original) skeleton with the same exporter;
    # only overall metric size and floor origin should differ at this check.
    # Designed proportions keep their original rest skeleton as an explicit
    # compatibility reference. Never bypass the source-preset mismatch check.
    reference=json.loads(arm['retarget_reference_rest']) if arm.get('retarget_reference_rest') else None
    if reference and not set(names).issubset(reference):
        raise ValueError('Variant is missing its original reference skeleton')
    ref_lengths={n:reference[n]['length'] if reference else arm.data.bones[n].length for n in names}
    ref_heads={n:Vector(reference[n]['head']) if reference else arm.data.bones[n].head_local for n in names}
    scale=statistics.median(ref_lengths[n]/source.data.bones[n].length for n in names if source.data.bones[n].length>.06)
    offsets=[arm.matrix_world @ ref_heads[n]-(source.matrix_world @ source.data.bones[n].head_local)*scale for n in names]
    offset=sum(offsets,Vector())/len(offsets)
    rest_error=max((v-offset).length for v in offsets)
    if rest_error>.003:raise ValueError(f'Source body preset does not match this doll (rest mismatch {rest_error:.4f} m)')
    mapping=Matrix.Scale(scale,4)
    mapping.translation=offset
    inv_map=mapping.inverted()
    expected={}
    for n in names:
        src_rest=source.matrix_world @ source.data.bones[n].matrix_local
        src_pose=source.matrix_world @ source.pose.bones[n].matrix
        dst_rest=arm.matrix_world @ arm.data.bones[n].matrix_local
        desired_world=mapping @ src_pose @ src_rest.inverted() @ inv_map @ dst_rest
        expected[n]=arm.matrix_world.inverted() @ desired_world
        if reference:
            # Preserve the new bone lengths/shoulder span while following the
            # inferred rotations. An absolute source joint copy would undo them.
            parent=arm.data.bones[n].parent
            if parent and parent.name in expected:
                expected[n].translation=(expected[parent.name] @ parent.matrix_local.inverted()
                                         @ arm.data.bones[n].head_local)
        arm.pose.bones[n].matrix=expected[n]
        bpy.context.view_layer.update()
    # Snap the existing handles to the transferred FK pose before restoring IK.
    for side in ('Left','Right'):
        for end in ('Hand','Foot'):
            ctl=arm.pose.bones[f'CTRL_{end}_{side}']
            ctl.matrix=expected[side+end]
    bpy.context.view_layer.update()
    for c,mute in constraints:c.mute=mute
    bends={}
    for side in ('Left','Right'):
        for mid,start,end,label in [('ForeArm','Arm','Hand','Elbow'),('Leg','UpLeg','Foot','Knee')]:
            bends[side+label]=fit_pole(arm,side,mid,start,end,label,expected)
    # Apply one global floor offset. This preserves a deliberately lifted foot.
    vertices=mesh_positions(mesh)
    floor_shift=-min(v.z for v in vertices)
    root=arm.pose.bones['CTRL_Root']
    matrix=root.matrix.copy()
    matrix.translation.z+=floor_shift
    root.matrix=matrix
    bpy.context.view_layer.update()
    shift=Vector((0,0,floor_shift))
    errors={n:(arm.pose.bones[n].head-(expected[n].translation+shift)).length for n in names}
    ik_errors={side+end:(arm.pose.bones[side+mid].tail-arm.pose.bones[f'CTRL_{end}_{side}'].head).length
               for side in ('Left','Right') for mid,end in [('ForeArm','Hand'),('Leg','Foot')]}
    if max(ik_errors.values())>.002 or max(errors.values())>.01:
        raise RuntimeError(f'Pose matching failed: joint {max(errors.values()):.4f} m, IK {max(ik_errors.values()):.4f} m')
    for obj in imported:bpy.data.objects.remove(obj,do_unlink=True)
    # Active pose remains static and editable. Keep the original fake-user presets.
    scene=bpy.context.scene
    scene.frame_set(1)
    scene.timeline_markers.clear()
    scene.timeline_markers.new(pose_label or 'Qwen21 - inferred pose',frame=1)
    if pose_id:
        arm['pose_library_id']=pose_id
        arm['pose_library_label']=pose_label or pose_id
        arm['pose_library_editing_test']='not_run_by_user_request'
    arm['pose_source']=str(source_path)
    arm['pose_source_sha256']=hashlib.sha256(source_path.read_bytes()).hexdigest()
    vertices=mesh_positions(mesh)
    low=Vector(tuple(min(v[i] for v in vertices) for i in range(3)))
    high=Vector(tuple(max(v[i] for v in vertices) for i in range(3)))
    center=(low+high)*.5
    scene.render.resolution_x=768
    scene.render.resolution_y=1024
    if pose_json:
        pose=json.loads(Path(pose_json).read_text(encoding='utf-8'))
        size=pose.get('image_size')
        if isinstance(size,dict) and 'height' in size and 'width' in size:
            scene.render.resolution_y=int(size['height'])
            scene.render.resolution_x=int(size['width'])
    scene.render.resolution_percentage=100
    cam=scene.camera
    cam.data.type='ORTHO'
    cam.location=center+Vector((0,-6,0))
    cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
    ratio=scene.render.resolution_x/scene.render.resolution_y
    cam.data.ortho_scale=max((high.z-low.z)*1.12,(high.x-low.x)/ratio*1.12)
    if portable_output:
        # AUTO sensor fit measures the larger image dimension. Also fit wide
        # floor poses without cropping their hands/feet in landscape previews.
        cam.data.ortho_scale*=max(1.,ratio)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_location=center
                area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion()
                area.spaces.active.region_3d.view_distance=cam.data.ortho_scale*1.35
    activate(arm,'POSE')
    bpy.ops.pose.select_all(action='DESELECT')
    arm.data.bones.active=arm.data.bones['Hips']
    arm.data.bones['Hips'].select=True
    output_path.parent.mkdir(parents=True,exist_ok=True)
    render_path=Path(render_path).resolve() if render_path else output_path.with_suffix('.png')
    scene.render.filepath=('//'+render_path.name if portable_output and render_path.parent==output_path.parent
                           else str(render_path))
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    export_pose(arm,output_path.with_name(output_path.stem+'_openpose'))
    bpy.ops.render.render(write_still=True)
    report={'base':str(base_path),'base_sha256':base_hash,'source_fbx':str(source_path),
            'retarget_mode':'reference-checked rotations with designed proportions' if reference else 'matching native skeleton',
            'output':str(output_path),'matched_bones':len(names),'rest_match_max_m':rest_error,
            'scale':scale,'ground_shift_m':floor_shift,'joint_position_errors_m':errors,
            'ik_target_errors_m':ik_errors,'pole_match_errors_m':bends,
            'constraint_count_before':len(constraints),'constraint_count_after':sum(len(p.constraints) for p in arm.pose.bones),
            'color_properties_retained':all(k in arm for k in ('Upper_color','Lower_color','Skin_color','Shoes_color')),
            'base_unchanged':hashlib.sha256(base_path.read_bytes()).hexdigest()==base_hash}
    if pose_id:
        report.update(pose_library_id=pose_id,pose_library_label=pose_label,
                      validation_scope='conversion_sanity_only; additional Blender editing tests not run')
    output_path.with_suffix('.validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('TRANSFERRED',output_path, 'max joint error',max(errors.values()),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('base_blend')
    p.add_argument('source_fbx')
    p.add_argument('output_blend')
    p.add_argument('--render')
    p.add_argument('--pose-json')
    p.add_argument('--pose-id')
    p.add_argument('--pose-label')
    p.add_argument('--portable-output',action='store_true')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    transfer(args.base_blend,args.source_fbx,args.output_blend,args.render,args.pose_json,
             pose_id=args.pose_id,pose_label=args.pose_label,portable_output=args.portable_output)
