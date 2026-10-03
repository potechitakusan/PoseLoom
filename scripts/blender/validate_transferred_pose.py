"""Reopen a transferred IK doll and verify editing without modifying the file."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0,str(Path(__file__).parent))
from pose_doll_tools import register


def validate(path):
    path=Path(path).resolve()
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(path))
    rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
    assert len(rigs)==1, 'Imported source rig must be removed'
    rig=rigs[0]
    mesh=next(o for o in bpy.context.scene.objects if o.type=='MESH' and o.parent==rig)
    constraints=[c for pb in rig.pose.bones for c in pb.constraints]
    assert len(constraints)==8 and all(not c.mute for c in constraints)
    assert sum(c.type=='IK' for c in constraints)==4
    assert len(rig.data.bones)==74
    assert not rig.animation_data.action
    original={p.name:p.matrix.copy() for p in rig.pose.bones}
    bpy.context.scene.frame_set(2)
    bpy.context.view_layer.update()
    frame_error=max((p.head-original[p.name].translation).length for p in rig.pose.bones)
    assert frame_error<1e-5, 'Frame change reset the imported pose'
    hand=rig.pose.bones['CTRL_Hand_Left']
    wrist=rig.pose.bones['LeftForeArm']
    old=wrist.tail.copy()
    matrix=hand.matrix.copy()
    matrix.translation+=(rig.pose.bones['LeftArm'].head-hand.head).normalized()*.04
    hand.matrix=matrix
    bpy.context.view_layer.update()
    movement=(wrist.tail-old).length
    hand_error=(wrist.tail-hand.head).length
    assert movement>.02 and hand_error<.002
    lower=tuple(mesh.data.materials[2].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value)
    rig['Upper_color']=[.6,.12,.02]
    rig.update_tag()
    bpy.context.view_layer.update()
    upper=tuple(mesh.data.materials[1].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value)
    assert abs(upper[0]-.6)<1e-5
    assert tuple(mesh.data.materials[2].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value)==lower
    register()
    assert bpy.ops.posedoll.preset(frame=40)=={'FINISHED'}
    preset_errors={s+end:(rig.pose.bones[s+mid].tail-rig.pose.bones[f'CTRL_{end}_{s}'].head).length
                   for s in ('Left','Right') for mid,end in [('ForeArm','Hand'),('Leg','Foot')]}
    assert max(preset_errors.values())<.002
    report={'blend':str(path),'bones':len(rig.data.bones),'constraints':len(constraints),
            'frame_change_max_m':frame_error,'hand_move_m':movement,'moved_hand_ik_error_m':hand_error,
            'independent_colors':True,'preset_ik_errors_m':preset_errors,
            'file_unchanged':hashlib.sha256(path.read_bytes()).hexdigest()==digest}
    path.with_suffix('.editing_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('blend')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    validate(args.blend)
