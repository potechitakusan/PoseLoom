"""Remove the other person with Qwen-Image 2.1, independently from one original.

This path does not require two people to be detected in the occluded source.
The two resulting images must each contain one detectable full-body person.
"""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from comfy_client import URL, run
from kit_config import CONFIG, CONFIG_DIR
from generate_qwen21_pose import build_workflow
from run_sam3dbody import release_cached_models, upload_image
from check_image_dwpose import check


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def default_subjects(order):
    if order[0]!=order[1]:
        names={'male':'adult man','female':'adult woman'}
        return [f'the {names[preset]} on the {side}' for preset,side in zip(order,('left','right'))]
    return ['the person on the left','the person on the right']


def edit_prompt(keep,remove):
    return (f'Edit <image1>. Keep only {keep}. Completely remove {remove}, including all of that '
            "person's limbs, hands, clothing and shadows. The result must show exactly ONE person: "
            f'{keep}. Preserve this remaining person\'s identity, clothing, body proportions, facing '
            'direction, head direction, body lean, joint positions and original pose as closely as possible. '
            'Do not change to a new pose, straighten the body, lower raised arms, or mirror the image. '
            'Where the removed person was covering the remaining person, reconstruct only the missing '
            'parts of the remaining body and clothes in an anatomically plausible continuation of the '
            'same pose. Keep the remaining hands and arms in their original positions even when their '
            'partner is gone. Fill the rest of the removed area with the existing background and floor. '
            'Keep the original camera, framing, scale and background. Show the entire remaining person '
            'including both feet. No extra person, no disembodied limbs, no text.')


def build_edit_workflow(image_filename,prompt,seed=20260926,steps=25,resolution=992):
    if CONFIG.get('edit_workflow'):
        from workflow_template import load, resolve
        graph=resolve(load(CONFIG_DIR/CONFIG['edit_workflow']),{
            'image':image_filename,'prompt':prompt,'seed':seed,'steps':steps,
            'resolution':resolution,'unet':CONFIG['qwen_unet'],'clip':CONFIG['qwen_clip'],
            'vae':CONFIG['qwen_vae'],'prefix':f'PoseLoom/remove_{seed}'})
        if graph.get('8',{}).get('class_type')!='SaveImage':raise ValueError('edit_workflow requires SaveImage node 8')
        return graph
    weights=build_workflow('',template=False)
    return {
        **{n:weights[n] for n in ('1','2','3')},
        '4':{'class_type':'LoadImage','inputs':{'image':image_filename}},
        '5':{'class_type':'TextEncodeQwenImage21','inputs':{
            'clip':['2',0],'vae':['3',0],'prompt':prompt,'negative_prompt':'',
            'resolution':resolution,'images.image_1':['4',0]}},
        '6':{'class_type':'KSampler','inputs':{'model':['1',0],
            'positive':['5',0],'negative':['5',1],'latent_image':['5',2],
            'seed':seed,'steps':steps,'cfg':1.,'sampler_name':'euler','scheduler':'simple','denoise':1.}},
        '7':{'class_type':'VAEDecode','inputs':{'samples':['6',0],'vae':['3',0]}},
        '8':{'class_type':'SaveImage','inputs':{'images':['7',0],'filename_prefix':f'PoseLoom/qwen21_remove_{seed}'}}}


def preview(source,images,path):
    canvas=Image.new('RGB',(1536,572),'#f4f5f7')
    draw=ImageDraw.Draw(canvas)
    from build_catalog import font as load_font
    font=load_font(22)
    for i,(file,label) in enumerate(zip([source,*images],['Original pair','Person 1: other person removed','Person 2: other person removed'])):
        with Image.open(file) as opened:thumb=ImageOps.contain(opened.convert('RGB'),(496,512))
        canvas.paste(thumb,(i*512+(512-thumb.width)//2,48+(512-thumb.height)//2))
        draw.text((i*512+12,14),label,fill='#182332',font=font)
    canvas.save(path)


def separate(image_path,output_dir,order=('male','female'),subjects=None,seed=20260926,
             steps=25,resolution=992,reuse=False,prepare_only=False):
    image_path=Path(image_path).resolve()
    out=Path(output_dir).resolve()
    edited=out/'removed_people'
    edited.mkdir(parents=True,exist_ok=True)
    subjects=list(subjects) if subjects else default_subjects(order)
    if len(subjects)!=2 or any(not s.strip() for s in subjects) or subjects[0].strip()==subjects[1].strip():
        raise ValueError('Specify two distinct descriptions of the people to keep')
    if not 64<=resolution<=2048 or resolution%32:
        raise ValueError('Edit resolution must be a multiple of 32 between 64 and 2048')
    if steps<1:raise ValueError('Edit steps must be positive')
    with Image.open(image_path) as im:width,height=im.size
    prompts=[edit_prompt(subjects[i],subjects[1-i]) for i in range(2)]
    recipe={'input_sha256':digest(image_path),'order':list(order),'subjects':subjects,
            'seed':seed,'steps':steps,'resolution':resolution,'prompts':prompts,
            'weights':{k:v['inputs'] for k,v in build_edit_workflow('',prompts[0]).items() if k in ('1','2','3')}}
    paths=[edited/f'person_{i+1}_{preset}.png' for i,preset in enumerate(order)]
    cache_path=edited/'edit_manifest.json'
    if reuse:
        cache=json.loads(cache_path.read_text(encoding='utf-8'))
        if cache.get('recipe')!=recipe or len(cache.get('images',[]))!=2 or any(not path.is_file() or digest(path)!=item['sha256'] for path,item in zip(paths,cache['images'])):
            raise ValueError('Saved edits do not match this image/settings; omit --reuse-edits to regenerate')
    else:
        uploaded=upload_image(image_path)
        workflows=[]
        for i in range(2):
            workflow=build_edit_workflow(uploaded,prompts[i],seed+i,steps,resolution)
            (edited/f'person_{i+1}_workflow_api.json').write_text(json.dumps(workflow,indent=2),encoding='utf-8')
            (edited/f'person_{i+1}_prompt.txt').write_text(prompts[i]+'\n',encoding='utf-8')
            workflows.append(workflow)
        if prepare_only:return workflows
        release_cached_models()
        for i,workflow in enumerate(workflows):
            history=run(workflow,edited/f'person_{i+1}_history.json',timeout=1800)
            images=history.get('outputs',{}).get('8',{}).get('images',[])
            if len(images)!=1:raise RuntimeError(f'Expected one person-removal output, got {images}')
            with urllib.request.urlopen(URL+'/view?'+urllib.parse.urlencode(images[0]),timeout=30) as response:
                paths[i].write_bytes(response.read())
            print('EDITED',paths[i],flush=True)
        cache_path.write_text(json.dumps({'recipe':recipe,'images':[{'path':str(p),'sha256':digest(p)} for p in paths]},indent=2),encoding='utf-8')
    preview(image_path,paths,out/'separation_preview.png')
    release_cached_models()
    people=[]
    for i,(preset,path) in enumerate(zip(order,paths)):
        check(path,edited/f'person_{i+1}_dwpose',expected_people=1)
        data=json.loads((edited/f'person_{i+1}_dwpose/keypoints.json').read_text(encoding='utf-8'))
        frame=data[0] if isinstance(data,list) else data
        points=np.asarray(frame['people'][0]['pose_keypoints_2d']).reshape(-1,3)
        points[:,0]*=width/frame['canvas_width']
        points[:,1]*=height/frame['canvas_height']
        visible=points[:14][points[:14,2]>0,:2]
        bbox=[float(visible[:,0].min()),float(visible[:,1].min()),float(visible[:,0].max()),float(visible[:,1].max())]
        if bbox[3]-bbox[1]<height*.15:raise RuntimeError(f'Edited person is too small to analyze: {path}')
        hips=[points[j,0] for j in (8,11) if points[j,2]>0]
        people.append({'id':f'person_{i+1}','preset':preset,'subject':subjects[i],
                       'analysis_image':str(path),'analysis_image_sha256':digest(path),
                       'bbox_xyxy':bbox,'hip_x_px':float(np.mean(hips)) if hips else (bbox[0]+bbox[2])/2})
    report={'input':str(image_path),'input_sha256':recipe['input_sha256'],'width':width,'height':height,
            'separation':'qwen-remove','method':'Qwen-Image 2.1 removes the other person; two independent edits of original',
            'preset_assignment':'explicit subject/order arguments','default_spacing_m':1.1,
            'occluded_parts':'Generated reconstruction, not measured ground truth','people':people}
    if digest(image_path)!=recipe['input_sha256']:raise RuntimeError('Source image changed during editing')
    (out/'person_selection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--order',nargs=2,choices=['male','female'],default=['male','female'])
    p.add_argument('--subjects',nargs=2)
    p.add_argument('--seed',type=int,default=20260926)
    p.add_argument('--steps',type=int,default=25)
    p.add_argument('--resolution',type=int,default=992)
    p.add_argument('--reuse-edits',action='store_true')
    p.add_argument('--prepare-only',action='store_true')
    args=p.parse_args()
    separate(args.image,args.output_dir,args.order,args.subjects,args.seed,args.steps,args.resolution,args.reuse_edits,args.prepare_only)
