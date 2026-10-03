"""Export a saved scene as BVH and a portable blend with embedded JSON.

Run with Blender: -b --python-exit-code 1 -P export_asset.py -- --jobs jobs.json
or --blend source.blend --output-dir new_folder --id pose_id.
The input file is never saved over. No rendering or inference is performed.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import bpy
from mathutils import Matrix

COPYRIGHT = 'Momentum Human Rig (MHR) — Copyright (c) Meta Platforms, Inc. and affiliates.'
NOTICE = (COPYRIGHT + '\nMHR-derived human mesh and skeleton: Apache License 2.0.\n'
          'https://github.com/facebookresearch/MHR\nhttps://www.apache.org/licenses/LICENSE-2.0\n'
          'Modified by the PoseLoom project: body proportions, IK controls, materials, '
          'pose transfer, scene layout and format export. No endorsement by Meta is implied.\n'
          'See the accompanying asset.json and distribution license documents.\n')


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def matrix(value):
    return [[round(float(x), 8) for x in row] for row in value]


def vector(value):
    return [round(float(x), 8) for x in value]


def activate(obj):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def depth(bone):
    return len(bone.parent_recursive)


def rig_metadata(rig):
    return {'object': rig.name, 'rig_version': rig.get('rig_version'),
            'matrix_world': matrix(rig.matrix_world),
            'collection': [c.name for c in rig.users_collection],
            'controls': [b.name for b in rig.data.bones if b.name.startswith('CTRL_')],
            'colors': {k: list(rig[k]) for k in ('Upper_color','Lower_color','Skin_color','Shoes_color') if k in rig},
            'bones': [{'name': b.name, 'parent': b.parent.name if b.parent else None,
                       'deform': b.bone.use_deform,
                       'head_world': vector(rig.matrix_world @ b.head),
                       'tail_world': vector(rig.matrix_world @ b.tail),
                       'rest_matrix_local': matrix(b.bone.matrix_local),
                       'pose_matrix': matrix(b.matrix), 'matrix_basis': matrix(b.matrix_basis),
                       'rotation_mode': b.rotation_mode,
                       'constraints': [{'name': c.name, 'type': c.type, 'influence': c.influence,
                                        'target': getattr(getattr(c, 'target', None), 'name', None),
                                        'subtarget': getattr(c, 'subtarget', None)} for c in b.constraints]}
                      for b in rig.pose.bones]}


def baked_copy(rig):
    """Copy the rest skeleton, then bake the evaluated pose without IK controls."""
    bones = sorted((b for b in rig.data.bones if not b.name.startswith('CTRL_')), key=depth)
    poses = {b.name: rig.matrix_world @ rig.pose.bones[b.name].matrix.copy() for b in bones}
    data = bpy.data.armatures.new(rig.name+'_ExportData')
    obj = bpy.data.objects.new(rig.name+'_Export', data)
    bpy.context.scene.collection.objects.link(obj)
    activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    for b in bones:
        eb = data.edit_bones.new(b.name)
        eb.matrix = rig.matrix_world @ b.matrix_local
        eb.length = b.length * rig.matrix_world.to_scale().length / math.sqrt(3)
        if b.parent and b.parent.name in data.edit_bones:
            eb.parent = data.edit_bones[b.parent.name]
        # Keep evaluated joint positions even where the source uses scaled/IK bones.
        # A connected copy would snap heads to tails before we bake the pose.
        eb.use_connect = False
        eb.inherit_scale = b.inherit_scale
        eb.use_inherit_rotation = b.use_inherit_rotation
        eb.use_local_location = b.use_local_location
    bpy.ops.object.mode_set(mode='OBJECT')
    for b in bones:
        pb = obj.pose.bones[b.name]
        pb.rotation_mode = 'QUATERNION'
        pb.matrix = poses[b.name]
        bpy.context.view_layer.update()
        for prop in ('location', 'rotation_quaternion', 'scale'):
            pb.keyframe_insert(data_path=prop, frame=1)
    errors={name:(obj.pose.bones[name].head-m.translation).length for name,m in poses.items()}
    if max(errors.values(),default=0) > .0001:
        raise RuntimeError(f'Baked skeleton mismatch: {max(errors.items(),key=lambda x:x[1])}')
    return obj


def embed(name, content):
    text=bpy.data.texts.get(name) or bpy.data.texts.new(name)
    text.clear();text.write(content)


def embed_json(name, value):
    embed(name,json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def export_one(job):
    source=Path(job['source']).resolve(); out=Path(job['output']).resolve()
    if source == out/'pose.blend':
        raise ValueError('Source and output must differ')
    source_sha=sha(source)
    asset={k:job[k] for k in ('id','name_ja','category','collection','kind','visual_review','prompt','seed',
                              'source_image_sha256','difference_ja','nearest_previous_id') if job.get(k) is not None}
    stamp={'source_sha256':source_sha,'exporter_sha256':sha(__file__),'id':job['id'],'frame':job.get('frame'),
           'metadata_sha256':hashlib.sha256(json.dumps(asset,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest(),
           'body_preset_sha256':sha(Path(job['body_preset'])) if job.get('body_preset') else None}
    if (out/'export.json').is_file():
        old=json.loads((out/'export.json').read_text(encoding='utf-8'))
        if old.get('stamp') == stamp and all((out/n).is_file() and sha(out/n)==h for n,h in old['sha256'].items()):
            print('REUSED',job['id'],flush=True); return
        raise FileExistsError(f'Changed export already exists; use a new output directory: {out}')
    out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    bpy.context.preferences.filepaths.save_version=0
    scene=bpy.context.scene
    scene.frame_set(int(job.get('frame', scene.frame_current)))
    bpy.context.view_layer.update()
    rigs=[o for o in scene.objects if o.type=='ARMATURE' and o.get('rig_version')]
    if not rigs:
        rigs=[o for o in scene.objects if o.type=='ARMATURE']
    metadata={'schema_version':2,'id':job['id'],'name_ja':job.get('name_ja',job['id']),
              'kind':job.get('kind','pose'),'units':'metres','up_axis':'Z','forward_axis':'-Y',
              'frame':scene.frame_current,'blender_version':bpy.app.version_string,
              'rigs':[rig_metadata(o) for o in rigs],
              'camera':None if not scene.camera else {'object':scene.camera.name,
                  'matrix_world':matrix(scene.camera.matrix_world),'type':scene.camera.data.type,
                  'ortho_scale':scene.camera.data.ortho_scale,'lens_mm':scene.camera.data.lens},
              'source_sha256':source_sha,'license':{'human_data':'Apache-2.0',
                   'origin':'Meta Momentum Human Rig (MHR)', 'notice':'../../../licenses.html',
                   'modifications':'PoseLoom proportions, IK, materials, pose transfer, scene and export'},
              'usage':{'saved_pose':'Keep the saved pose; omit the scene spec pose field.',
                       'append_collection':'Character' if 'Character' in bpy.data.collections else None,
                       'bvh':'One frame, Y up, centimetres, baked rotations from the neutral rest skeleton.',
                       'clip_studio_validation':'not_tested_in_application'},
              'files':{'blend':'pose.blend'}}
    for index in range(len(rigs)):
        metadata['files']['bvh' if len(rigs)==1 else f'bvh_person_{index+1}']='pose.bvh' if len(rigs)==1 else f'person_{index+1}.bvh'
    if not rigs:
        metadata['license']={'human_data':None,'origin':'PoseLoom primitive scene', 'notice':'../../../licenses.html'}
    # Attribution travels with the binary. Original data is left unchanged on disk.
    embed('ASSET_LICENSE.txt',NOTICE if rigs else 'PoseLoom primitive scene; see embedded asset.json.\n')
    license_root=Path(__file__).resolve().parents[2]/'licenses/sam3dbody'
    if rigs:
        for name in ('LICENSE-MHR','NOTICE-MHR'):
            embed(name+'.txt',(license_root/name).read_text(encoding='utf-8'))
    if job.get('body_preset'):
        embed('body_preset.json',Path(job['body_preset']).read_text(encoding='utf-8'))
    asset.update(schema_version=2,files=metadata['files'],source_blend_sha256=source_sha,
                 license=metadata['license'],license_status='upstream_confirmed_local_draft',
                 embedded_metadata={'asset':'asset.json','rig':'rig.json'})
    embed_json('rig.json',metadata);embed_json('asset.json',asset)
    scene['asset_id']=job['id']; scene['asset_source_sha256']=source_sha
    scene['asset_metadata_text']='asset.json';scene['rig_metadata_text']='rig.json'
    scene.render.filepath='//preview.png'
    for rig in rigs:
        if 'pose_source' in rig:
            rig['pose_source']='Source recorded by hash in asset.json'
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'pose.blend'),compress=True)
    # Build records stay in the export cache. The catalog copies only blend/BVH.
    write_json(out/'rig.json',metadata);write_json(out/'asset.json',asset)
    previous=Path(job['previous_export']) if job.get('previous_export') else None
    if previous and (previous/'export.json').is_file():
        old=json.loads((previous/'export.json').read_text(encoding='utf-8'))
        if old['stamp']['source_sha256']!=source_sha:
            raise ValueError('Previous BVH belongs to another source: '+job['id'])
        for key,name in metadata['files'].items():
            if key=='blend':continue
            if sha(previous/name)!=old['sha256'][name]:raise ValueError('Previous BVH hash mismatch: '+name)
            shutil.copy2(previous/name,out/name)
        files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='export.json'}
        write_json(out/'export.json',{'stamp':stamp,'sha256':files,'bvh_reused_from_validated_export':True})
        print('EXPORTED',job['id'],len(rigs),'BVH reused',flush=True);return
    # Save the editable original first, then bake temporary bones for BVH only.
    scene.frame_start=scene.frame_end=1
    # Mesh deformation is irrelevant to BVH. Hide it before the per-bone updates
    # so a dense skinned mesh is not re-evaluated for every joint.
    for obj in list(scene.objects):
        if obj.type=='MESH':obj.hide_viewport=True
    bpy.context.view_layer.update()
    baked=[baked_copy(r) for r in rigs]
    for index,arm in enumerate(baked):
        name='pose.bvh' if len(baked)==1 else f'person_{index+1}.bvh'
        desired={p.name:p.matrix.copy() for p in arm.pose.bones}
        arm.animation_data_clear()
        axis=Matrix.Rotation(-math.pi/2,4,'X')
        arm.data.transform(axis)
        for bone in sorted(arm.data.bones,key=depth):
            arm.pose.bones[bone.name].matrix=axis@desired[bone.name]
            bpy.context.view_layer.update()
        activate(arm)
        bpy.ops.export_anim.bvh(filepath=str(out/name),global_scale=100.0,
            frame_start=1,frame_end=1,rotate_mode='XYZ',root_transform_only=False)
    files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='export.json'}
    write_json(out/'export.json',{'stamp':stamp,'sha256':files})
    print('EXPORTED',job['id'],len(rigs),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs',type=Path)
    parser.add_argument('--blend',type=Path)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--id')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if args.jobs:
        jobs=json.loads(args.jobs.read_text(encoding='utf-8'))
    elif args.blend and args.output_dir and args.id:
        jobs=[{'source':str(args.blend),'output':str(args.output_dir),'id':args.id}]
    else:
        parser.error('Use --jobs or --blend + --output-dir + --id')
    for job in jobs: export_one(job)


if __name__=='__main__': main()
