"""Optional Blender sidebar and dependency-free OpenPose export.

Run this text once in Blender's Text Editor. The rig itself needs no add-on.
OpenPose drawing follows COCO-18 colors/edges; hands and dense face are omitted.
"""
import json
import math
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

FRAMES = [(1, '直立'), (20, '腕上げ'), (40, 'しゃがみ'), (60, '歩行'), (80, 'ひねり'), (100, '踏み込み')]
PAIRS = [(1,2),(1,5),(2,3),(3,4),(5,6),(6,7),(1,8),(8,9),(9,10),(1,11),(11,12),(12,13),(1,0),(0,14),(14,16),(0,15),(15,17)]
COLORS = [(255,0,0),(255,85,0),(255,170,0),(255,255,0),(170,255,0),(85,255,0),
          (0,255,0),(0,255,85),(0,255,170),(0,255,255),(0,170,255),(0,85,255),
          (0,0,255),(85,0,255),(170,0,255),(255,0,255),(255,0,170),(255,0,85)]


def get_rig():
    obj = bpy.context.object
    while obj:
        if obj.type == 'ARMATURE' and obj.get('rig_version'): return obj
        obj=obj.parent
    return next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE' and o.get('rig_version')), None)


def body_keypoints(rig):
    """Return COCO-18 joints in world space; head landmarks are approximations."""
    pb = rig.pose.bones
    names = [None, 'Neck', 'RightArm', 'RightForeArm', 'RightHand', 'LeftArm', 'LeftForeArm', 'LeftHand',
             'RightUpLeg', 'RightLeg', 'RightFoot', 'LeftUpLeg', 'LeftLeg', 'LeftFoot']
    points = [rig.matrix_world @ pb[n].head if n else None for n in names]
    height_scale = rig.get('height_m', 1.78)/1.78
    head = pb['Head']
    rest_head = head.bone.head_local
    delta = rig.matrix_world @ head.matrix @ head.bone.matrix_local.inverted()
    # Positions relative to the rest head joint in the character coordinate system.
    face = [(0, -.095, .035), (-.033, -.083, .064), (.033, -.083, .064),
            (-.075, -.009, .036), (.075, -.009, .036)]
    face = [delta @ (rest_head+Vector(p)*height_scale) for p in face]
    points[0] = face[0]
    points.extend(face[1:])
    return points


def export_pose(rig, prefix):
    """Project the evaluated Blender joints into the active camera, save JSON + PNG."""
    return export_poses([rig],prefix)


def export_poses(rigs, prefix):
    """Project one or more independent rigs into one OpenPose image and JSON."""
    import numpy as np  # bundled with Blender
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    width = round(scene.render.resolution_x*scene.render.resolution_percentage/100)
    height = round(scene.render.resolution_y*scene.render.resolution_percentage/100)
    all_points=[]
    people=[]
    for rig in rigs:
        projected = [world_to_camera_view(scene, scene.camera, p) for p in body_keypoints(rig)]
        points = [(p.x*width, (1-p.y)*height, 1.0 if p.z > 0 and 0<=p.x<=1 and 0<=p.y<=1 else 0.0) for p in projected]
        all_points.append(points)
        people.append({'person_id':[-1],'pose_keypoints_2d':[v for p in points for v in p],
                       'face_keypoints_2d':[],'hand_left_keypoints_2d':[],'hand_right_keypoints_2d':[]})
    payload = {'version':1.3, 'canvas_width':width, 'canvas_height':height,
               'people':people,
               'source':'Blender camera-projected COCO-18 joints; approximate head landmarks; no occlusion filtering'}
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix('.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    pixels = np.zeros((height,width,4),dtype=np.float32)
    pixels[:,:,3] = 1
    def paint(x,y,mask,color):
        pixels[y,x,:3] = np.where(mask[...,None], np.asarray(color,dtype=np.float32)/255, pixels[y,x,:3])
    def disk(point,color,radius):
        x,y,c = point
        if not c:return
        x0,x1=max(0,int(x-radius)),min(width,int(x+radius)+2)
        y0,y1=max(0,int(y-radius)),min(height,int(y+radius)+2)
        yy,xx=np.mgrid[y0:y1,x0:x1]
        paint(xx,yy,(xx-x)**2+(yy-y)**2<=radius*radius,color)
    radius=max(3,width/190)
    for points in all_points:
        for i,(a,b) in enumerate(PAIRS):
            x0,y0,c0=points[a]; x1,y1,c1=points[b]
            if not(c0 and c1):continue
            xmin,xmax=max(0,int(min(x0,x1)-radius)),min(width,int(max(x0,x1)+radius)+2)
            ymin,ymax=max(0,int(min(y0,y1)-radius)),min(height,int(max(y0,y1)+radius)+2)
            yy,xx=np.mgrid[ymin:ymax,xmin:xmax]
            dx,dy=x1-x0,y1-y0
            t=np.clip(((xx-x0)*dx+(yy-y0)*dy)/max(dx*dx+dy*dy,1e-8),0,1)
            mask=(xx-x0-t*dx)**2+(yy-y0-t*dy)**2<=radius*radius
            paint(xx,yy,mask,tuple(v*.65 for v in COLORS[i]))
        for i,p in enumerate(points):disk(p,COLORS[i],radius*1.45)
    image = bpy.data.images.new('Pose export',width=width,height=height,alpha=True)
    image.colorspace_settings.name = 'sRGB'
    image.pixels.foreach_set(np.flipud(pixels).ravel())
    image.filepath_raw = str(prefix.with_suffix('.png'))
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)
    return str(prefix.with_suffix('.png'))


class POSEDOLL_OT_preset(bpy.types.Operator):
    bl_idname = 'posedoll.preset'
    bl_label = 'Apply pose preset'
    bl_options = {'REGISTER','UNDO'}
    frame: bpy.props.IntProperty(default=1)
    def execute(self, context):
        rig=get_rig()
        if not rig:return {'CANCELLED'}
        action=bpy.data.actions.get(rig.get('preset_action',''))
        if not action:
            self.report({'ERROR'},'Preset action missing')
            return {'CANCELLED'}
        rig.animation_data_create()
        # Preset actions key controllers and torso only. Reset the unkeyed FK
        # shoulder/finger transforms left by an inferred pose before evaluating.
        rig.animation_data.action=None
        for pb in rig.pose.bones:
            pb.matrix_basis.identity()
        rig.animation_data.action=action
        context.scene.frame_set(self.frame)
        matrices={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
        rig.animation_data.action=None  # current pose remains editable without frame resets
        for n,m in matrices.items():rig.pose.bones[n].matrix_basis=m
        context.view_layer.update()
        return {'FINISHED'}


class POSEDOLL_OT_export(bpy.types.Operator):
    bl_idname='posedoll.export'
    bl_label='Export OpenPose PNG + JSON'
    def execute(self, context):
        rig=get_rig()
        if not rig:return {'CANCELLED'}
        prefix=Path(bpy.path.abspath('//'))/'exports'/f'{rig.name}_pose'
        path=export_pose(rig,prefix)
        self.report({'INFO'},path)
        return {'FINISHED'}


class POSEDOLL_OT_select_rig(bpy.types.Operator):
    bl_idname='posedoll.select_rig'
    bl_label='Select person'
    rig_name:bpy.props.StringProperty()
    def execute(self,context):
        rig=context.scene.objects.get(self.rig_name)
        if not rig:return {'CANCELLED'}
        if context.object and context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        rig.select_set(True)
        context.view_layer.objects.active=rig
        bpy.ops.object.mode_set(mode='POSE')
        return {'FINISHED'}


class POSEDOLL_OT_export_scene(bpy.types.Operator):
    bl_idname='posedoll.export_scene'
    bl_label='Export all people to OpenPose'
    def execute(self,context):
        rigs=sorted((o for o in context.scene.objects if o.type=='ARMATURE' and o.get('rig_version')),key=lambda o:o.name)
        if not rigs:return {'CANCELLED'}
        path=export_poses(rigs,Path(bpy.path.abspath('//'))/'exports'/'all_people_pose')
        self.report({'INFO'},path)
        return {'FINISHED'}


class POSEDOLL_PT_controls(bpy.types.Panel):
    bl_label='Pose Doll / ポーズ人形'
    bl_idname='POSEDOLL_PT_controls'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='Pose Doll'
    def draw(self, context):
        layout=self.layout
        rig=get_rig()
        if not rig:
            layout.label(text='Open male.blend / female_anime_v2.blend')
            return
        rigs=[o for o in context.scene.objects if o.type=='ARMATURE' and o.get('rig_version')]
        if len(rigs)>1:
            layout.label(text='操作する人物')
            for person in rigs:
                layout.operator('posedoll.select_rig',text=person.name,depress=person==rig).rig_name=person.name
        layout.label(text='手足: G 移動 / R 回転')
        layout.label(text='腰: G / 胸・頭: R')
        for i in range(0,len(FRAMES),2):
            row=layout.row(align=True)
            for frame,label in FRAMES[i:i+2]:row.operator('posedoll.preset',text=label).frame=frame
        layout.label(text='プリセット適用後は自由に編集できます')
        for prop,label in [('Upper_color','上半身の服'),('Lower_color','下半身の服'),('Skin_color','肌'),('Shoes_color','靴')]:
            layout.prop(rig,f'["{prop}"]',text=label)
        layout.operator('posedoll.export',text='棒人形 PNG + JSON を出力')
        if len(rigs)>1:layout.operator('posedoll.export_scene',text='全員の棒人形をまとめて出力')


CLASSES=(POSEDOLL_OT_preset,POSEDOLL_OT_export,POSEDOLL_OT_select_rig,POSEDOLL_OT_export_scene,POSEDOLL_PT_controls)
def register():
    for cls in CLASSES:
        old=getattr(bpy.types,cls.__name__,None)
        if old:bpy.utils.unregister_class(old)
        bpy.utils.register_class(cls)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':area.spaces.active.show_region_ui=True


if __name__=='__main__':register()
