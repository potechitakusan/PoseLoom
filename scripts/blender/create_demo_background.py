"""Create a small original room for the included staging example (metres)."""
import argparse
import sys
from pathlib import Path
import bpy
from mathutils import Vector


def create(output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    def material(name, color):
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*color, 1)
        return mat
    wall = material('Warm plaster', (.57, .54, .48))
    floor = material('Blue grey floor', (.22, .29, .33))
    trim = material('Window trim', (.07, .1, .13))
    wood = material('Bench wood', (.35, .20, .10))
    def box(name, location, size, mat):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj = bpy.context.object
        obj.name = name
        obj.dimensions = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(mat)
        return obj
    box('Room floor', (0, 0, -.1), (8, 8, .2), floor)
    box('Back wall', (0, 2.5, 1.7), (8, .15, 3.4), wall)
    box('Left wall', (-3.1, 0, 1.7), (.15, 5, 3.4), wall)
    box('Window frame', (.3, 2.37, 2), (2.3, .1, 1.7), trim)
    glass = material('Window light', (.6, .78, .88))
    glass.use_nodes = True
    bsdf = glass.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (.6, .78, .88, 1)
    bsdf.inputs['Emission Color'].default_value = (.6, .78, .88, 1)
    bsdf.inputs['Emission Strength'].default_value = .5
    box('Window pane', (.3, 2.3, 2), (2.12, .04, 1.52), glass)
    box('Window mullion vertical', (.3, 2.25, 2), (.06, .06, 1.55), trim)
    box('Window mullion horizontal', (.3, 2.25, 2), (2.15, .06, .06), trim)
    box('Bench seat', (-1.4, 1.75, .48), (1.7, .48, .1), wood)
    for x in (-2.05, -.75):
        box('Bench support', (x, 1.75, .22), (.1, .4, .44), trim)
    world = bpy.data.worlds.new('Room world')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.25, .3, .4, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .45
    scene.world = world
    for name, pos, power, size in [('Room key', (0, -3, 5), 1000, 5), ('Room fill', (-2, -1, 3), 450, 4)]:
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.size = power, size
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = pos
        obj.rotation_euler = (Vector((0, .5, .8))-obj.location).to_track_quat('-Z', 'Y').to_euler()
    data = bpy.data.cameras.new('Background camera')
    camera = bpy.data.objects.new(data.name, data)
    scene.collection.objects.link(camera)
    camera.location = (3.4, -7, 3.1)
    camera.rotation_euler = (Vector((0, .75, 1))-camera.location).to_track_quat('-Z', 'Y').to_euler()
    data.type, data.ortho_scale = 'ORTHO', 4.7
    scene.camera = camera
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1024, 768
    scene.render.resolution_percentage = 100
    scene.render.filepath = '//background.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    create(args.output)
