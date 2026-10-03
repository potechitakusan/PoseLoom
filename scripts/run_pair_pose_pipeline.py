"""Generate/select a pair image, infer each person, and assemble editable dolls.

Without --image, generate the pair with local Qwen-Image 2.1. By default the
original image is passed to both SAM3D analyses with person-selection masks.
--separation qwen-remove instead edits the original into two single-person images.
--order explicitly assigns the model presets from left to right.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from comfy_client import ROOT
from kit_config import ASSETS, preset
from run_sam3dbody import BLENDER_EXE, process_image
from segment_pair_image import segment
from check_image_dwpose import check
from separate_pair_qwen import separate as separate_qwen

FEMALE_MODELS={'anime-v2':'female_anime_v2'}


def command(args,log):
    print('RUN',subprocess.list2cmdline([str(a) for a in args]),flush=True)
    with Path(log).open('w',encoding='utf-8') as handle:
        result=subprocess.run([str(a) for a in args],cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
    if result.returncode:
        tail=Path(log).read_text(encoding='utf-8',errors='replace')[-2500:]
        raise RuntimeError(f'Command failed ({result.returncode}); see {log}\n{tail}')


def manual_selection(image,masks,out,order):
    with Image.open(image) as source:width,height=source.size
    people=[]
    for i,(mask,preset) in enumerate(zip(masks,order)):
        with Image.open(mask) as source:
            if source.size!=(width,height):raise ValueError('Manual mask must have the original image size')
            binary=np.asarray(source.convert('RGB'))[:,:,0]>127
        yy,xx=np.where(binary)
        if not len(xx):raise ValueError('Manual mask is empty')
        path=out/f'person_{i+1}_{preset}_mask.png'
        Image.fromarray(binary.astype(np.uint8)*255).save(path)
        people.append({'id':f'person_{i+1}','preset':preset,'mask':str(path),
                       'mask_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                       'bbox_xyxy':[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],
                       'hip_x_px':float(np.median(xx))})
    report={'input':str(image),'input_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
            'width':width,'height':height,'method':'User-supplied individual masks; original image unchanged',
            'preset_assignment':'explicit left-to-right CLI order','people':people}
    (out/'person_selection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def comparison(image,out,separation='mask'):
    sheet=Image.new('RGB',(1536,590),'#f4f5f7')
    draw=ImageDraw.Draw(sheet)
    from build_catalog import font as load_font
    font=load_font(22)
    small=load_font(18)
    for i,(path,title,caption) in enumerate([
            (image,'1  Pair reference image','Qwen person-removal mode' if separation=='qwen-remove' else 'One unchanged input image'),
            (out/'pair_posed.png','2  Blender: two editable rigs','Separate IK and clothing colors'),
            (out/'dwpose_result/dwpose.png','3  ComfyUI DWPose','Two independently detected people')]):
        picture=ImageOps.contain(Image.open(path).convert('RGB'),(496,512))
        sheet.paste(picture,(512*i+(512-picture.width)//2,48+(512-picture.height)//2))
        draw.text((512*i+14,13),title,fill='#182332',font=font)
        draw.text((512*i+14,565),caption,fill='#334155',font=small)
    sheet.save(out/'comparison.png')


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',type=Path,help='Existing pair image; omit to generate with Qwen-Image 2.1')
    p.add_argument('--prompt-file',type=Path,default=ROOT/'input/qwen21_pair_prompt.txt')
    p.add_argument('--seed',type=int,default=20260924)
    p.add_argument('--steps',type=int,default=25)
    p.add_argument('--width',type=int,default=1024)
    p.add_argument('--height',type=int,default=1024)
    p.add_argument('--output-dir',type=Path,default=ROOT/'output/qwen21_pair_pose')
    p.add_argument('--order',nargs=2,choices=['male','female'],default=['male','female'])
    p.add_argument('--female-style',choices=list(FEMALE_MODELS),default='anime-v2',
                   help='This distribution includes the female anime v2 doll')
    p.add_argument('--masks',nargs=2,type=Path,help='Optional two white-person masks, in the same left-to-right order')
    p.add_argument('--separation',choices=['mask','qwen-remove'],default='mask',help='How to isolate each person for SAM3D')
    p.add_argument('--subjects',nargs=2,help='Descriptions of person 1 and person 2 to keep in Qwen edits')
    p.add_argument('--edit-seed',type=int,default=20260926)
    p.add_argument('--edit-steps',type=int,default=25)
    p.add_argument('--edit-resolution',type=int,default=992)
    p.add_argument('--reuse-edits',action='store_true',help='Reuse hash-verified edits with identical image/settings')
    p.add_argument('--separate-only',action='store_true',help='Save separation results for review, without running SAM3D or Blender')
    p.add_argument('--spacing',type=float,help='Override horizontal hip spacing in metres')
    p.add_argument('--assemble-only',action='store_true',help='Reassemble already generated people; do not infer or change their poses')
    return p


def main():
    p=parser()
    args=p.parse_args()
    if args.separation=='qwen-remove' and args.masks:p.error('--masks cannot be combined with --separation qwen-remove')
    if args.separation!='qwen-remove' and (args.subjects or args.reuse_edits):p.error('--subjects and --reuse-edits require --separation qwen-remove')
    if args.assemble_only and args.separate_only:p.error('--assemble-only and --separate-only cannot be combined')
    if args.female_style!='standard' and 'female' in args.order and not (args.assemble_only or args.separate_only):
        model=ASSETS/f'{FEMALE_MODELS[args.female_style]}.blend'
        if not model.is_file():
            p.error(f'Create {model} with scripts/blender/create_anime_female.py first')
    out=args.output_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    logs=out/'logs'
    logs.mkdir(exist_ok=True)
    selection_path=out/'person_selection.json'
    if args.assemble_only:
        selection=json.loads(selection_path.read_text(encoding='utf-8'))
        image=Path(selection['input'])
        if hashlib.sha256(image.read_bytes()).hexdigest()!=selection['input_sha256']:
            raise ValueError('Source image has changed; run the analysis again')
    else:
        image=args.image.resolve() if args.image else out/'qwen21_pose.png'
        if not args.image:
            command([sys.executable,'-X','utf8',ROOT/'scripts/generate_qwen21_pose.py',
                     '--prompt-file',args.prompt_file.resolve(),'--output-dir',out,'--seed',args.seed,
                     '--steps',args.steps,'--width',args.width,'--height',args.height,
                     '--negative','cropped feet, cropped hands, extra limbs, missing limbs, crowd, text, watermark'],logs/'generation.log')
        if args.separation=='qwen-remove':
            selection=separate_qwen(image,out,args.order,args.subjects,args.edit_seed,
                                    args.edit_steps,args.edit_resolution,args.reuse_edits)
        else:
            selection=manual_selection(image,args.masks,out,args.order) if args.masks else segment(image,out,args.order)
        if args.separate_only:
            print('SEPARATED',selection_path,flush=True)
            return
        for person in selection['people']:
            gender=person['preset']
            person_dir=out/'people'/f"{person['id']}_{gender}"
            person_dir.mkdir(parents=True,exist_ok=True)
            analysis_image=Path(person.get('analysis_image',image))
            if person.get('analysis_image_sha256') and hashlib.sha256(analysis_image.read_bytes()).hexdigest()!=person['analysis_image_sha256']:
                raise ValueError(f'Edited image changed before analysis: {analysis_image}')
            paths=process_image(analysis_image,person_dir/'analysis',gender,True,
                                preset(gender),mask_path=person.get('mask'))
            model_name=FEMALE_MODELS[args.female_style] if gender=='female' else gender
            person['model']=model_name
            command([BLENDER_EXE,'-b','--python-exit-code',1,'-P',ROOT/'scripts/blender/retarget_pose_doll.py','--',
                     ASSETS/f'{model_name}.blend',paths['fbx'],person_dir/'posed.blend',
                     '--pose-json',paths['pose']],logs/f"{person['id']}_retarget.log")
        selection_path.write_text(json.dumps(selection,indent=2),encoding='utf-8')
    poses=[out/'people'/f"{person['id']}_{person['preset']}"/'posed.blend' for person in selection['people']]
    for path in poses:
        if not path.is_file():raise FileNotFoundError(path)
    assemble=[BLENDER_EXE,'-b','--python-exit-code',1,'-P',ROOT/'scripts/blender/assemble_pose_pair.py','--',
              *poses,selection_path,out/'pair_posed.blend']
    spacing=args.spacing if args.spacing is not None else selection.get('default_spacing_m')
    if spacing is not None:assemble+=['--spacing',spacing]
    command(assemble,logs/'assemble.log')
    command([BLENDER_EXE,'-b','--python-exit-code',1,'-P',ROOT/'scripts/blender/validate_pose_pair.py','--',
             out/'pair_posed.blend'],logs/'validation.log')
    check(out/'pair_posed.png',out/'dwpose_result',expected_people=2)
    comparison(image,out,selection.get('separation','mask'))
    launcher=f'@echo off\n"{BLENDER_EXE}" "%~dp0pair_posed.blend" --python "{ROOT / "scripts/blender/pose_doll_tools.py"}"\n'
    (out/'Open_Pair.cmd').write_text(launcher,encoding='utf-8')
    manifest={'input':selection['input'],'input_sha256':selection['input_sha256'],
              'blend':str(out/'pair_posed.blend'),'people':selection['people'],
              'source_image_unchanged':hashlib.sha256(image.read_bytes()).hexdigest()==selection['input_sha256'],
              'separation':selection.get('separation','mask'),
              'mode':selection['method']+' -> two SAM3D inferences -> one Blender scene'}
    (out/'pair_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('COMPLETE',out/'pair_posed.blend',flush=True)


if __name__=='__main__':main()
