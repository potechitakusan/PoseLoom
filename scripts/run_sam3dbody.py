"""Run local ComfyUI SAM3D analysis and save the actual pose and provenance.

The single-image CLI is retained. --gender female --export-fbx enables the
new IK-doll transfer; --body-preset locks the source to the doll shape.
"""
import argparse
import hashlib
import json
import mimetypes
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from comfy_client import NODE, ROOT, URL, request, run
from kit_config import ASSETS

COMFY_URL = URL
from kit_config import BLENDER_EXE


def release_cached_models():
    """Make room for SAM3D's isolated worker after Qwen image generation."""
    req = urllib.request.Request(URL+'/free',
        data=json.dumps({'unload_models':True,'free_memory':True}).encode(),
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:
        response.read()  # ComfyUI /free returns an empty HTTP 200 body.


def load_body_preset(gender='male', preset_path=None):
    path = Path(preset_path) if preset_path else ASSETS / f'sources/{gender}_preset.json'
    preset = json.loads(path.read_text(encoding='utf-8'))
    if not all(k in preset for k in ('body_params', 'bone_lengths', 'blendshapes')):
        raise ValueError(f'Incomplete body preset: {path}')
    return json.dumps(preset)


def check_server():
    try:
        request('/system_stats')
        return True
    except Exception:
        return False


def upload_image(path):
    path = Path(path)
    raw = path.read_bytes()
    name = 'sam3d_' + hashlib.sha256(raw).hexdigest()[:16] + path.suffix.lower()
    boundary = '----SAM3D' + uuid.uuid4().hex
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
            f'Content-Type: {mime}\r\n\r\n').encode() + raw + f'\r\n--{boundary}--\r\n'.encode()
    req = urllib.request.Request(URL+'/upload/image', data=body,
                                 headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)
    return '/'.join(filter(None, [result.get('subfolder'), result['name']]))


def build_workflow_prompt(image_filename, output_bvh_filename, output_image_prefix,
                         gender='male', output_fbx_filename=None, preset_path=None, mask_filename=None):
    preset = load_body_preset(gender, preset_path)
    workflow = {
        '1': {'class_type':'LoadSAM3DBodyModel', 'inputs':{'device_mode':'Auto'}},
        '2': {'class_type':'LoadImage', 'inputs':{'image':image_filename}},
        '3': {'class_type':'SAM3DBodyProcessToJson', 'inputs':{
            'model':['1',0], 'image':['2',0], 'bbox_threshold':.8, 'inference_type':'full'}},
        '4': {'class_type':'PreviewAny', 'inputs':{'source':['3',0]}},
        '5': {'class_type':'SAM3DBodyExportPosedBVH', 'inputs':{
            'model':['1',0], 'body_preset_json':preset, 'pose_json':['3',0],
            'blender_exe':BLENDER_EXE, 'output_filename':str(output_bvh_filename)}},
        '6': {'class_type':'SAM3DBodyRenderFromPoseAndBodyPresetJson', 'inputs':{
            'model':['1',0], 'pose_json':['3',0], 'body_preset_json':preset,
            'offset_x':0., 'offset_y':0., 'scale_offset':1., 'camera_yaw_deg':0.,
            'camera_pitch_deg':0., 'width':1024, 'height':1024, 'pose_adjust':0.}},
        '7': {'class_type':'PreviewImage', 'inputs':{'images':['6',0]}},
        '8': {'class_type':'PreviewAny', 'inputs':{'source':['5',0]}}
    }
    if output_fbx_filename:
        workflow['9'] = {'class_type':'SAM3DBodyExportRiggedFBX', 'inputs':{
            'model':['1',0], 'body_preset_json':preset, 'pose_json':['3',0],
            'blender_exe':BLENDER_EXE, 'output_filename':str(output_fbx_filename)}}
        workflow['10'] = {'class_type':'PreviewAny', 'inputs':{'source':['9',0]}}
    if mask_filename:
        workflow['11'] = {'class_type':'LoadImageMask','inputs':{'image':mask_filename,'channel':'red'}}
        workflow['3']['inputs']['mask'] = ['11',0]
    return workflow


def process_image(image_path, output_dir='output/sam3dbody', gender='male', export_fbx=False,
                  preset_path=None, timeout=900, mask_path=None, *, workflow_runner=None):
    image_path = Path(image_path).resolve()
    if mask_path:
        from PIL import Image
        with Image.open(image_path) as img, Image.open(mask_path) as mask:
            if mask.size!=img.size:raise ValueError('Mask size must match the original image')
            if mask.convert('RGB').getchannel('R').getextrema()==(0,0):raise ValueError('Target mask is empty')
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stem = image_path.stem
    paths = {'bvh':out/f'sam3d_{stem}.bvh', 'pose':out/f'{stem}_pose.json',
             'render':out/f'{stem}_sam3d_render.png'}
    if export_fbx: paths['fbx'] = out/f'sam3d_{stem}.fbx'
    workflow = build_workflow_prompt(upload_image(image_path), paths['bvh'].as_posix(), stem,
                                    gender, paths.get('fbx'), preset_path,
                                    upload_image(mask_path) if mask_path else None)
    (out/f'{stem}_workflow_api.json').write_text(json.dumps(workflow, indent=2), encoding='utf-8')
    (out/f'{stem}_body_preset.json').write_text(load_body_preset(gender,preset_path),encoding='utf-8')
    release_cached_models()
    history = (workflow_runner or run)(workflow, out/f'{stem}_history.json', timeout=timeout)
    outputs = history.get('outputs',{})
    pose = json.loads(outputs['4']['text'][0])
    if not isinstance(pose,dict) or pose.get('body_pose_params') is None:
        raise RuntimeError('SAM3D did not return a body pose')
    paths['pose'].write_text(json.dumps(pose,indent=2), encoding='utf-8')
    images = outputs.get('7',{}).get('images',[])
    if len(images) != 1: raise RuntimeError(f'Expected one SAM3D render, got {images}')
    with urllib.request.urlopen(URL+'/view?'+urllib.parse.urlencode(images[0]), timeout=30) as response:
        paths['render'].write_bytes(response.read())
    for kind,path in paths.items():
        if not path.is_file() or path.stat().st_size < 100:
            raise RuntimeError(f'Missing or empty {kind} output: {path}')
    manifest = {'input':str(image_path),'input_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest(),
                'gender':gender,'outputs':{k:str(v) for k,v in paths.items()}}
    if mask_path:
        manifest['mask']=str(Path(mask_path).resolve())
        manifest['mask_sha256']=hashlib.sha256(Path(mask_path).read_bytes()).hexdigest()
    (out/f'{stem}_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2),flush=True)
    return paths


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',nargs='?',type=Path)
    p.add_argument('--output-dir',type=Path,default=ROOT/'output/sam3dbody')
    p.add_argument('--gender',choices=['male','female'],default='male')
    p.add_argument('--body-preset',type=Path)
    p.add_argument('--export-fbx',action='store_true')
    p.add_argument('--timeout',type=int,default=900)
    p.add_argument('--mask',type=Path,help='White target-person mask, same pixel size as the original image')
    args=p.parse_args()
    images=[args.image] if args.image else sorted((ROOT/'input/test_images').glob('*.jpg'))
    for image in images:
        process_image(image,args.output_dir,args.gender,args.export_fbx,args.body_preset,args.timeout,args.mask)


if __name__=='__main__':main()
