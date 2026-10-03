"""Append two editable posed dolls into one scene with approximate image layout."""
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).parent))
from rig_utils import activate
from retarget_pose_doll import mesh_positions
from pose_doll_tools import export_poses, register


def assemble(first,second,selection_path,output_path,spacing=None):
    sources=[Path(first).resolve(),Path(second).resolve()]
    output_path=Path(output_path).resolve()
    if output_path in sources:raise ValueError('Save the pair to a new file')
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]
    selection=json.loads(Path(selection_path).read_text(encoding='utf-8'))
    bpy.ops.wm.open_mainfile(filepath=str(sources[0]))
    scene=bpy.context.scene
    rig1=next(o for o in scene.objects if o.type=='ARMATURE' and o.get('rig_version'))
    activate(rig1)
    bpy.data.collections['Character'].name='Person 1 - '+selection['people'][0]['preset']
    bpy.data.collections['Widgets'].name='Person 1 widgets'
    before=set(scene.objects)
    with bpy.data.libraries.load(str(sources[1]),link=False) as (src,dst):
        dst.collections=[n for n in src.collections if n in ('Character','Widgets')]
        dst.actions=[n for n in src.actions if '6 Pose Presets' in n]
    for collection in dst.collections:
        if collection:
            scene.collection.children.link(collection)
            collection.name='Person 2 widgets' if collection.name.startswith('Widgets') else 'Person 2 - '+selection['people'][1]['preset']
            if collection.name=='Person 2 widgets':
                for obj in collection.objects:obj.hide_set(True)
    added=set(scene.objects)-before
    rig2=next(o for o in added if o.type=='ARMATURE' and o.get('rig_version'))
    preset=next((a for a in dst.actions if a and a.name.startswith(selection['people'][1]['preset'].capitalize())),None)
    if preset:
        preset.use_fake_user=True
        rig2['preset_action']=preset.name
    rigs=[rig1,rig2]
    meshes=[next(o for o in scene.objects if o.type=='MESH' and o.parent==rig) for rig in rigs]
    bpy.context.view_layer.update()
    lengths=[]
    for mesh,person in zip(meshes,selection['people']):
        verts=mesh_positions(mesh)
        lengths.append((max(v.z for v in verts)-min(v.z for v in verts))/(person['bbox_xyxy'][3]-person['bbox_xyxy'][1]))
    mpp=statistics.median(lengths)
    centers=[p['hip_x_px'] for p in selection['people']]
    middle=sum(centers)/2
    for i,rig in enumerate(rigs):
        target=(centers[i]-middle)*mpp if spacing is None else (i-.5)*spacing
        hip=rig.matrix_world @ rig.pose.bones['Hips'].head
        rig.location.x+=target-hip.x
        rig['pair_person_id']=selection['people'][i]['id']
        rig['pair_preset']=selection['people'][i]['preset']
        rig['pair_source_image']=selection['input']
        # Refresh the embedded helper; source models may contain an older text.
    for old in list(bpy.data.texts):
        if old.name.startswith('pose_doll_tools.py'):bpy.data.texts.remove(old)
    bpy.data.texts.load(str(Path(__file__).with_name('pose_doll_tools.py')))
    bpy.context.view_layer.update()
    verts=[v for mesh in meshes for v in mesh_positions(mesh)]
    low=Vector(tuple(min(v[i] for v in verts) for i in range(3)))
    high=Vector(tuple(max(v[i] for v in verts) for i in range(3)))
    center=(low+high)/2
    scene.render.resolution_x=selection['width']
    scene.render.resolution_y=selection['height']
    scene.render.resolution_percentage=100
    camera=scene.camera
    camera.location=center+Vector((0,-7,0))
    camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
    ratio=scene.render.resolution_x/scene.render.resolution_y
    camera.data.type='ORTHO'
    camera.data.ortho_scale=max(high.z-low.z,(high.x-low.x)/ratio)*1.13
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_location=center
                area.spaces.active.region_3d.view_rotation=camera.rotation_euler.to_quaternion()
                area.spaces.active.region_3d.view_distance=camera.data.ortho_scale*1.35
    scene['pair_selection_json']=str(Path(selection_path).resolve())
    scene['pair_layout']=('Explicit horizontal hip spacing; common floor; depth not reconstructed jointly'
                          if spacing is not None else 'Image hip horizontal spacing; common floor; depth not reconstructed jointly')
    activate(rig1,'POSE')
    register()
    output_path.parent.mkdir(parents=True,exist_ok=True)
    scene.render.filepath=str(output_path.with_suffix('.png'))
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    export_poses(rigs,output_path.with_stem(output_path.stem+'_openpose').with_suffix(''))
    bpy.ops.render.render(write_still=True)
    report={'output':str(output_path),'source_image':selection['input'],'source_image_sha256':selection['input_sha256'],
            'people':[{'rig':r.name,'preset':r['pair_preset'],'location':list(r.location),
                       'bones':len(r.data.bones),'constraints':sum(len(pb.constraints) for pb in r.pose.bones)} for r in rigs],
            'layout':scene['pair_layout'],'meters_per_pixel_estimate':mpp,
            'source_blends_unchanged':all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in zip(sources,hashes))}
    output_path.with_suffix('.assembly.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('ASSEMBLED',output_path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('first')
    p.add_argument('second')
    p.add_argument('selection_json')
    p.add_argument('output_blend')
    p.add_argument('--spacing',type=float,help='Override horizontal hip spacing in metres')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    assemble(args.first,args.second,args.selection_json,args.output_blend,args.spacing)
