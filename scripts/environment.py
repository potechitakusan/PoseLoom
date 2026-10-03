"""Read-only inventory by default; explicit automatic/manual download support."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.parse
import urllib.request
from kit_config import ROOT, COMFY, URL

NODES = {
    'sam3d': ('https://github.com/tori29umai0123/ComfyUI-SAM3DBody_utills.git', 'ComfyUI-SAM3DBody_utills'),
    'dwpose': ('https://github.com/Fannovel16/comfyui_controlnet_aux.git', 'comfyui_controlnet_aux'),
    'gguf': ('https://github.com/city96/ComfyUI-GGUF.git', 'ComfyUI-GGUF'),
}
def fetch(url, target, expected=None):
    if urllib.parse.urlparse(url).scheme != 'https':
        raise ValueError('Use a public HTTPS model/template URL')
    if target.exists():raise FileExistsError(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    part=target.with_name(target.name+'.part')
    if part.exists():raise FileExistsError(part)
    with urllib.request.urlopen(url, timeout=120) as r, part.open('xb') as f:
        if 'text/html' in r.headers.get('Content-Type',''):raise ValueError('URL returned HTML, not a downloadable file')
        shutil.copyfileobj(r,f,1024*1024)
    with part.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    if not part.stat().st_size or expected and digest.lower()!=expected.lower():
        raise ValueError('Empty download or SHA-256 mismatch; .part retained')
    part.rename(target)
    print(json.dumps({'file':str(target),'bytes':target.stat().st_size,'sha256':digest}))

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('inspect')
    n=sub.add_parser('node');n.add_argument('name',choices=NODES);n.add_argument('--mode',choices=['manual','automatic'],default='manual')
    n.add_argument('--comfy-python',type=Path);n.add_argument('--revision',help='Reviewed commit or tag; omitted means upstream default branch')
    m=sub.add_parser('model');m.add_argument('--url',required=True);m.add_argument('--directory',choices=['diffusion_models','unet','text_encoders','vae','loras','sam3dbody','annotators'],required=True)
    m.add_argument('--filename',required=True);m.add_argument('--sha256');m.add_argument('--mode',choices=['manual','automatic'],default='manual')
    t=sub.add_parser('template');t.add_argument('--name',default='image_qwen_image');t.add_argument('--revision',default='main');t.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.command=='inspect':
        data={'comfy_root':str(COMFY),'url':URL,'node_folders':{k:(COMFY/'custom_nodes'/v[1]).is_dir() for k,v in NODES.items()}}
        try:
            with urllib.request.urlopen(URL+'/system_stats',timeout=10) as r:data['system_stats']=json.load(r)
            with urllib.request.urlopen(URL+'/object_info',timeout=30) as r:info=json.load(r)
            data['nodes']=sorted(info)
            data['loaders']={k:info[k].get('input') for k in ['UNETLoader','CLIPLoader','VAELoader','LoadSAM3DBodyModel','DWPreprocessor'] if k in info}
        except Exception as exc:data['api_error']=str(exc)
        print(json.dumps(data,ensure_ascii=False,indent=2));return
    if args.command=='node':
        repo,name=NODES[args.name];target=COMFY/'custom_nodes'/name
        print(json.dumps({'repo':repo,'target':str(target),'mode':args.mode,'revision':args.revision,'instructions':'Clone or manually extract here. Use ComfyUI Python for requirements.txt; SAM3D also requires install.py. Restart idle ComfyUI afterwards.'},indent=2))
        if args.mode=='manual':return
        if not COMFY.is_dir():raise FileNotFoundError(COMFY)
        if not args.comfy_python or not args.comfy_python.is_file():p.error('--comfy-python must be the existing ComfyUI interpreter')
        if target.exists():raise FileExistsError('Existing node left intact: '+str(target))
        subprocess.run(['git','clone',repo,str(target)],check=True)
        if args.revision:subprocess.run(['git','-C',str(target),'checkout',args.revision],check=True)
        subprocess.run([str(args.comfy_python.resolve()),'-m','pip','install','-r',str(target/'requirements.txt')],check=True)
        if args.name=='sam3d':subprocess.run([str(args.comfy_python.resolve()),str(target/'install.py')],cwd=target,check=True)
        return
    if args.command=='model':
        if Path(args.filename).name!=args.filename or any(c in args.filename for c in '/\\:') or args.filename in ('.','..'):p.error('filename must be a basename')
        target=COMFY/'models'/args.directory/args.filename
        print(json.dumps({'url':args.url,'target':str(target),'mode':args.mode},indent=2))
        if args.mode=='automatic':
            if not COMFY.is_dir():raise FileNotFoundError(COMFY)
            fetch(args.url,target,args.sha256)
        return
    if not all(c.isalnum() or c in '_-' for c in args.name):p.error('Invalid template name')
    revision=urllib.parse.quote(args.revision,safe='')
    fetch(f'https://raw.githubusercontent.com/Comfy-Org/workflow_templates/{revision}/templates/{args.name}.json',args.output)

if __name__=='__main__':main()
