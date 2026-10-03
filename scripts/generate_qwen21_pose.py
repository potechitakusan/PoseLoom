"""Generate a reproducible pose reference with locally installed Qwen-Image 2.1."""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from comfy_client import ROOT, URL, run
from kit_config import CONFIG, CONFIG_DIR


def build_workflow(prompt, seed=20260923, steps=25, width=768, height=1024, negative=None, *, template=True):
    if template and CONFIG.get('generation_workflow'):
        from workflow_template import load, resolve
        workflow = resolve(load(CONFIG_DIR / CONFIG['generation_workflow']), {
            'prompt':prompt, 'negative':negative or '', 'seed':seed, 'steps':steps,
            'width':width, 'height':height, 'unet':CONFIG['qwen_unet'],
            'clip':CONFIG['qwen_clip'], 'vae':CONFIG['qwen_vae'],
            'prefix':f'PoseLoom/reference_{seed}'})
        if workflow.get('9',{}).get('class_type') not in ('SaveImage','SaveImageAdvanced'):
            raise ValueError('generation_workflow must use SaveImage or SaveImageAdvanced node 9')
        return workflow
    # Standard text encoders avoid the template converter's incorrect min=0
    # autogrow validation. With no reference image these encode the same text.
    return {
        '1': {'class_type':'UNETLoader','inputs':{'unet_name':CONFIG['qwen_unet'],'weight_dtype':'default'}},
        '2': {'class_type':'CLIPLoader','inputs':{'clip_name':CONFIG['qwen_clip'],'type':'qwen_image','device':CONFIG.get('clip_device','default')}},
        '3': {'class_type':'VAELoader','inputs':{'vae_name':CONFIG['qwen_vae']}},
        '4': {'class_type':'CLIPTextEncode','inputs':{'clip':['2',0],'text':prompt}},
        '5': {'class_type':'CLIPTextEncode','inputs':{'clip':['2',0],'text':negative if negative is not None else 'cropped feet, cropped hands, extra limbs, missing limbs, multiple people, text, watermark'}},
        '6': {'class_type':'EmptySD3LatentImage','inputs':{'width':width,'height':height,'batch_size':1}},
        '7': {'class_type':'KSampler','inputs':{'model':['1',0],'positive':['4',0],'negative':['5',0],
            'latent_image':['6',0],'seed':seed,'steps':steps,'cfg':1.0,'sampler_name':'euler','scheduler':'simple','denoise':1.0}},
        '8': {'class_type':'VAEDecodeTiled','inputs':{'samples':['7',0],'vae':['3',0],
              'tile_size':256,'overlap':64,'temporal_size':64,'temporal_overlap':8}} if CONFIG.get('tiled_vae') else
             {'class_type':'VAEDecode','inputs':{'samples':['7',0],'vae':['3',0]}},
        '9': {'class_type':'SaveImage','inputs':{'images':['8',0],'filename_prefix':f'PoseLoom/qwen21_pose_{seed}'}}
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--prompt-file',type=Path,default=ROOT/'input/qwen21_pose_prompt.txt')
    p.add_argument('--output-dir',type=Path,default=ROOT/'output/qwen21_female_pose')
    p.add_argument('--seed',type=int,default=20260923)
    p.add_argument('--steps',type=int,default=25)
    p.add_argument('--width',type=int,default=768)
    p.add_argument('--height',type=int,default=1024)
    p.add_argument('--negative')
    p.add_argument('--prepare-only',action='store_true')
    args=p.parse_args()
    out=args.output_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    prompt=args.prompt_file.read_text(encoding='utf-8').strip()
    if min(args.width,args.height)<64 or args.width%8 or args.height%8:
        p.error('Image dimensions must be at least 64 and multiples of 8')
    workflow=build_workflow(prompt,args.seed,args.steps,args.width,args.height,args.negative)
    (out/'generation_workflow_api.json').write_text(json.dumps(workflow,indent=2),encoding='utf-8')
    (out/'prompt.txt').write_text(prompt+'\n',encoding='utf-8')
    if args.prepare_only:
        print(out/'generation_workflow_api.json')
        return
    history=run(workflow,out/'generation_history.json',timeout=1800)
    images=history.get('outputs',{}).get('9',{}).get('images',[])
    if len(images)!=1:raise RuntimeError(f'Expected one generated image, got {images}')
    with urllib.request.urlopen(URL+'/view?'+urllib.parse.urlencode(images[0]),timeout=30) as response:
        (out/'qwen21_pose.png').write_bytes(response.read())
    print('GENERATED',out/'qwen21_pose.png',flush=True)


if __name__=='__main__':main()
