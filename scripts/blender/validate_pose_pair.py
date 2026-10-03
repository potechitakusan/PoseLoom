"""Verify both rigs remain independent after appending, without saving edits."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
sys.path.insert(0,str(Path(__file__).parent))
from pose_doll_tools import export_pose, export_poses, register
from retarget_pose_doll import mesh_positions


def validate(path):
    path=Path(path).resolve()
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(path))
    rigs=sorted((o for o in bpy.context.scene.objects if o.type=='ARMATURE'),key=lambda r:r['pair_person_id'])
    assert len(rigs)==2
    checks=[]
    register()
    export_poses(rigs,path.parent/'validation_exports'/'pair')
    export_pose(rigs[0],path.parent/'validation_exports'/'single')
    for name,count in [('pair',2),('single',1)]:
        data=json.loads((path.parent/'validation_exports'/f'{name}.json').read_text())
        assert len(data['people'])==count
        assert all(sum(p['pose_keypoints_2d'][2::3])==18 for p in data['people'])
    initial={r.name:{p.name:p.matrix.copy() for p in r.pose.bones} for r in rigs}
    bpy.context.scene.frame_set(2)
    for r in rigs:
        assert not r.animation_data.action
        assert max((p.head-initial[r.name][p.name].translation).length for p in r.pose.bones)<1e-5
    for i,rig in enumerate(rigs):
        other=rigs[1-i]
        mesh=next(o for o in bpy.context.scene.objects if o.type=='MESH' and o.parent==rig)
        other_mesh=next(o for o in bpy.context.scene.objects if o.type=='MESH' and o.parent==other)
        constraints=[c for pb in rig.pose.bones for c in pb.constraints]
        assert len(rig.data.bones)==74 and len(constraints)==8
        assert all(not c.mute and c.target==rig for c in constraints)
        floor=min(v.z for v in mesh_positions(mesh))
        assert abs(floor)<.003
        bpy.ops.posedoll.select_rig(rig_name=rig.name)
        assert bpy.context.object==rig and rig.mode=='POSE'
        other_pose={p.name:p.matrix.copy() for p in other.pose.bones}
        hand=rig.pose.bones['CTRL_Hand_Left']
        wrist=rig.pose.bones['LeftForeArm']
        old=wrist.tail.copy()
        matrix=hand.matrix.copy()
        matrix.translation+=(rig.pose.bones['LeftArm'].head-hand.head).normalized()*.04
        hand.matrix=matrix
        bpy.context.view_layer.update()
        movement=(wrist.tail-old).length
        assert movement>.02 and (wrist.tail-hand.head).length<.003
        assert max((p.head-other_pose[p.name].translation).length for p in other.pose.bones)<1e-5
        other_colors=[tuple(m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value) for m in other_mesh.data.materials]
        lower=tuple(mesh.data.materials[2].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value)
        rig['Upper_color']=[.25,.7,.1]
        rig.update_tag()
        bpy.context.view_layer.update()
        assert abs(mesh.data.materials[1].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value[0]-.25)<1e-5
        assert tuple(mesh.data.materials[2].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value)==lower
        assert [tuple(m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value) for m in other_mesh.data.materials]==other_colors
        assert bpy.ops.posedoll.preset(frame=40)=={'FINISHED'}
        bpy.context.view_layer.update()
        assert max((p.head-other_pose[p.name].translation).length for p in other.pose.bones)<1e-5
        preset_errors=[(rig.pose.bones[s+mid].tail-rig.pose.bones[f'CTRL_{end}_{s}'].head).length
                       for s in ('Left','Right') for mid,end in [('ForeArm','Hand'),('Leg','Foot')]]
        assert max(preset_errors)<.003
        checks.append({'rig':rig.name,'bones':74,'constraints':8,'hand_move_m':movement,
                       'independent_pose':True,'independent_colors':True,'independent_preset':True,'floor_min_m':floor})
    report={'people':checks,'pair_openpose_people':2,'single_export_people':1,
            'file_unchanged':hashlib.sha256(path.read_bytes()).hexdigest()==digest}
    path.with_suffix('.editing_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('blend')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    validate(args.blend)
