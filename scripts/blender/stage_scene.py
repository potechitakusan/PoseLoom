"""Append independent pose dolls to a background; preserve its camera unless specified."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(Path(__file__).parent))
from pose_doll_tools import register, export_poses

from kit_config import MODELS
POSES = {'stand': 1, 'arms_up': 20, 'crouch': 40, 'walk': 60, 'twist': 80, 'lunge': 100}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def activate(rig):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')


def append_character(source, person):
    before = set(bpy.context.scene.objects)
    with bpy.data.libraries.load(str(source), link=False) as (src, dst):
        if 'Character' not in src.collections:
            raise ValueError(f'Expected a single-person Character collection: {source}')
        dst.collections = [n for n in ('Character', 'Widgets') if n in src.collections]
        action_names = [n for n in src.actions if '6 Pose Presets' in n]
        dst.actions = list(action_names)
    for collection in dst.collections:
        bpy.context.scene.collection.children.link(collection)
        bpy.context.view_layer.update()
        widget = collection.name.startswith('Widgets')
        collection.name = person['id'] + (' - Widgets' if widget else ' - Character')
        if widget:
            for obj in list(collection.all_objects):
                if obj is None:
                    continue
                obj.hide_set(True)
                obj.hide_render = True
    rigs = [o for o in set(bpy.context.scene.objects)-before if o.type == 'ARMATURE' and o.get('rig_version')]
    if len(rigs) != 1:
        raise ValueError(f'Expected one supported rig in {source}')
    rig = rigs[0]
    actions = dict(zip(action_names, dst.actions))
    action = actions.get(rig.get('preset_action'))
    if not action:
        raise ValueError(f'Missing preset action: {source}')
    action.use_fake_user = True
    rig['preset_action'] = action.name
    rig.name = person['id']
    activate(rig)
    if 'pose' in person:
        pose = person['pose']
        if pose not in POSES:
            raise ValueError(f'Unknown pose: {pose}; use {list(POSES)}')
        if bpy.ops.posedoll.preset(frame=POSES[pose]) != {'FINISHED'}:
            raise RuntimeError('Failed to apply preset')
    elif rig.animation_data and rig.animation_data.action:
        # Base model uses frame 1; an inferred .blend has no active animation.
        if bpy.ops.posedoll.preset(frame=1) != {'FINISHED'}:
            raise RuntimeError('Failed to freeze base pose')
    rig.location = person.get('location', [0, 0, 0])
    rig.rotation_euler = [0, 0, math.radians(person.get('rotation_z_deg', 0))]
    scale = float(person.get('scale', 1))
    if scale <= 0:
        raise ValueError('Character scale must be positive')
    rig.scale = [scale]*3
    for key, prop in [('upper', 'Upper_color'), ('lower', 'Lower_color'),
                      ('skin', 'Skin_color'), ('shoes', 'Shoes_color')]:
        if key in person.get('colors', {}):
            value = person['colors'][key]
            if len(value) != 3 or not all(0 <= n <= 1 for n in value):
                raise ValueError('Colors require three linear RGB values between 0 and 1')
            rig[prop] = value
    rig.update_tag()
    bpy.context.view_layer.update()
    return rig


def basic_stage():
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    world = bpy.data.worlds.new('Kit studio')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.12, .14, .18, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .5
    scene.world = world
    bpy.ops.mesh.primitive_plane_add(size=200)
    bpy.context.object.name = 'Kit floor'
    mat = bpy.data.materials.new('Kit floor neutral')
    mat.diffuse_color = (.27, .3, .34, 1)
    bpy.context.object.data.materials.append(mat)
    for name, loc, power in [('Key', (2, -4, 5), 600), ('Fill', (-3, -2, 3), 350), ('Rim', (1, 3, 4), 500)]:
        data = bpy.data.lights.new('Kit '+name, 'AREA')
        data.energy, data.size = power, 4
        obj = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (Vector((0, 0, 1))-obj.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True


def stage(spec_path, output, no_render=False):
    spec_path, output = Path(spec_path).resolve(), Path(output).resolve()
    spec = json.loads(spec_path.read_text(encoding='utf-8-sig'))
    relative = lambda value: (spec_path.parent/Path(value)).resolve()
    people = spec['characters']
    if not people or len({p['id'] for p in people}) != len(people):
        raise ValueError('Use at least one character, with unique ids')
    sources = [(relative(p['blend']) if 'blend' in p else MODELS[p['model']]) for p in people]
    background = relative(spec['background']) if spec.get('background') else None
    inputs = sources + ([background] if background else [])
    if output in inputs or output.exists():
        raise ValueError('Save the scene to a new .blend path')
    hashes = {str(p): digest(p) for p in inputs}
    if background:
        bpy.ops.wm.open_mainfile(filepath=str(background))
        if abs(bpy.context.scene.unit_settings.scale_length-1) > 1e-6:
            raise ValueError('Prepare the background with Unit Scale 1 (one Blender unit = one metre)')
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        basic_stage()
    scene = bpy.context.scene
    original_camera = scene.camera
    original_frame = scene.frame_current
    register()
    rigs = [append_character(source, person) for source, person in zip(sources, people)]
    scene.frame_set(original_frame)
    if 'resolution' in spec or not background:
        width, height = spec.get('resolution', [1024, 1024])
        if min(width, height) < 64:
            raise ValueError('Resolution must be at least 64 pixels')
        scene.render.resolution_x, scene.render.resolution_y = width, height
        scene.render.resolution_percentage = 100
    camera = spec.get('camera')
    if camera or not scene.camera:
        camera = camera or {'location': [3, -6, 2.8], 'target': [0, 0, .95], 'ortho_scale': 3.8}
        data = bpy.data.cameras.new('Kit camera')
        obj = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(obj)
        obj.location = camera['location']
        obj.rotation_euler = (Vector(camera['target'])-obj.location).to_track_quat('-Z', 'Y').to_euler()
        data.type = camera.get('type', 'ORTHO')
        data.ortho_scale = camera.get('ortho_scale', 3.8)
        data.lens = camera.get('lens_mm', 50)
        scene.camera = obj
    scene.render.image_settings.file_format = 'PNG'
    if 'transparent' in spec:
        scene.render.film_transparent = bool(spec['transparent'])
    for old in list(bpy.data.texts):
        if old.name.startswith('pose_doll_tools.py'):
            bpy.data.texts.remove(old)
    bpy.data.texts.load(str(Path(__file__).with_name('pose_doll_tools.py')))
    bpy.context.view_layer.update()
    activate(rigs[0])
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
    output.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = '//'+output.with_suffix('.png').name
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    export_poses(rigs, output.with_name(output.stem+'_openpose'))
    if not no_render:
        bpy.ops.render.render(write_still=True)
    report = {'spec': str(spec_path), 'blend': output.name,
              'render': None if no_render else output.with_suffix('.png').name,
              'openpose': output.stem+'_openpose.png', 'keypoints': output.stem+'_openpose.json',
              'background_camera_preserved': bool(original_camera and scene.camera == original_camera),
              'people': [{'id': r.name, 'bones': len(r.data.bones),
                          'constraints': sum(len(p.constraints) for p in r.pose.bones),
                          'preset_action': r['preset_action'], 'location': list(r.location)} for r in rigs],
              'input_sha256': hashes, 'inputs_unchanged': all(digest(Path(p)) == h for p, h in hashes.items())}
    output.with_suffix('.scene.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--no-render', action='store_true')
    args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    stage(args.spec, args.output, args.no_render)
