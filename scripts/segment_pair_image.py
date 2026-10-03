"""Select two people in an unchanged image with DWPose points and SAM 3.1 masks.

Body presets are explicitly assigned in left-to-right order, not inferred from
appearance. Each mask preserves the original image canvas and coordinates.
"""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image
import numpy as np
import cv2

from check_image_dwpose import check
from comfy_client import URL, run
from run_sam3dbody import release_cached_models, upload_image


def person_points(person,width,height,canvas_width,canvas_height):
    points=np.asarray(person['pose_keypoints_2d'],dtype=float).reshape(-1,3)
    points[:,0]*=width/canvas_width
    points[:,1]*=height/canvas_height
    if any(points[i,2]<=0 for i in (1,2,5,8,11)):
        raise ValueError('Neck, shoulders and hips must be visible for automatic person selection; supply masks instead')
    shoulder=(points[2,:2]+points[5,:2])/2
    hip=(points[8,:2]+points[11,:2])/2
    inside=[shoulder*.65+hip*.35,shoulder*.25+hip*.75]
    if points[0,2]>0:inside.append(points[0,:2])
    # Clothing boundaries can make a torso-only click select only the shirt.
    # Include interior limb points so trousers, skin and shoes join the mask.
    for a,b in ((8,9),(9,10),(11,12),(12,13),(2,3),(3,4),(5,6)):
        if points[a,2]>0 and points[b,2]>0:
            inside.append((points[a,:2]+points[b,:2])/2)
    prompts=[{'x':round(float(p[0])),'y':round(float(p[1]))} for p in inside]
    return float(hip[0]),prompts,points


def segment(image_path,output_dir,order=('male','female')):
    image_path=Path(image_path).resolve()
    out=Path(output_dir).resolve()
    out.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(image_path.read_bytes()).hexdigest()
    check(image_path,out/'dwpose_source',expected_people=2)
    frames=json.loads((out/'dwpose_source/keypoints.json').read_text(encoding='utf-8'))
    frame=frames[0] if isinstance(frames,list) else frames
    with Image.open(image_path) as image:width,height=image.size
    selected=sorted((person_points(p,width,height,frame['canvas_width'],frame['canvas_height']) for p in frame['people']),key=lambda x:x[0])
    workflow={
        '1':{'class_type':'LoadImage','inputs':{'image':upload_image(image_path)}},
        '2':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':'sam3.1_multiplex_fp16.safetensors'}}}
    for i,item in enumerate(selected):
        n=3+3*i
        workflow[str(n)]={'class_type':'SAM3_Detect','inputs':{
            'model':['2',0],'image':['1',0],'threshold':.5,'refine_iterations':2,
            'individual_masks':False,'positive_coords':json.dumps(item[1]),
            'negative_coords':json.dumps(selected[1-i][1])}}
        workflow[str(n+1)]={'class_type':'MaskToImage','inputs':{'mask':[str(n),0]}}
        workflow[str(n+2)]={'class_type':'PreviewImage','inputs':{'images':[str(n+1),0]}}
    (out/'segmentation_workflow_api.json').write_text(json.dumps(workflow,indent=2),encoding='utf-8')
    release_cached_models()
    history=run(workflow,out/'segmentation_history.json')
    people=[]
    masks=[]
    for i,(preset,item) in enumerate(zip(order,selected)):
        images=history['outputs'][str(5+3*i)]['images']
        if len(images)!=1:raise RuntimeError('Expected one mask per selected person')
        path=out/f'person_{i+1}_{preset}_mask.png'
        with urllib.request.urlopen(URL+'/view?'+urllib.parse.urlencode(images[0]),timeout=30) as response:
            path.write_bytes(response.read())
        with Image.open(path) as mask:
            if mask.size!=(width,height):raise RuntimeError('Mask canvas differs from source image')
            arr=np.asarray(mask.convert('L'))>127
        # Tiny disconnected mask fragments can otherwise enlarge SAM3D's crop
        # to include the other person's shoe. Keep the selected person's body.
        raw_path=path.with_stem(path.stem+'_raw')
        raw_path.write_bytes(path.read_bytes())
        count,labels,stats,_=cv2.connectedComponentsWithStats(arr.astype(np.uint8),connectivity=8)
        if count<=1:raise RuntimeError(f'Empty person mask: {path}')
        arr=labels==(1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA])))
        Image.fromarray(arr.astype(np.uint8)*255).save(path)
        if not .01<arr.mean()<.65:raise RuntimeError(f'Invalid person mask area: {path}')
        yy,xx=np.where(arr)
        points=item[2]
        inside=sum(bool(arr[min(height-1,max(0,round(p[1]))),min(width-1,max(0,round(p[0])))]) for p in points[:14] if p[2]>0)
        if inside<10:raise RuntimeError(f'Mask misses body joints ({inside}/14): {path}; supply a corrected mask')
        masks.append(arr)
        people.append({'id':f'person_{i+1}','preset':preset,'mask':str(path),
                       'mask_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                       'bbox_xyxy':[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],
                       'hip_x_px':item[0],'body_points_in_mask':inside,'selection_points':item[1]})
    overlap=float(np.logical_and(*masks).sum()/max(1,np.logical_or(*masks).sum()))
    if overlap>.15:raise RuntimeError(f'Person masks overlap too much ({overlap:.1%}); supply separate masks')
    if people[0]['bbox_xyxy']==people[1]['bbox_xyxy']:raise RuntimeError('Both selections returned the same person')
    report={'input':str(image_path),'input_sha256':digest,'width':width,'height':height,
            'method':'DWPose points -> SAM3.1 instance masks, largest component; unchanged original image',
            'preset_assignment':'explicit left-to-right CLI order','mask_iou':overlap,'people':people}
    assert hashlib.sha256(image_path.read_bytes()).hexdigest()==digest
    (out/'person_selection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--order',nargs=2,choices=['male','female'],default=['male','female'])
    args=p.parse_args()
    segment(args.image,args.output_dir,args.order)
