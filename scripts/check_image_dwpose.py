"""Check an arbitrary image with local ComfyUI DWPose and keep its outputs."""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

from comfy_client import URL, run
from run_sam3dbody import upload_image


def check(image,output_dir,expected_people=1):
    image=Path(image).resolve()
    out=Path(output_dir).resolve()
    out.mkdir(parents=True,exist_ok=True)
    workflow={
        '1':{'class_type':'LoadImage','inputs':{'image':upload_image(image)}},
        '2':{'class_type':'DWPreprocessor','inputs':{'image':['1',0],'detect_hand':'disable',
            'detect_body':'enable','detect_face':'disable','resolution':768,
            'bbox_detector':'yolox_l.onnx','pose_estimator':'dw-ll_ucoco_384.onnx',
            'scale_stick_for_xinsr_cn':'disable'}},
        '3':{'class_type':'PreviewImage','inputs':{'images':['2',0]}},
        '4':{'class_type':'PreviewAny','inputs':{'source':['2',1]}}}
    (out/'workflow_api.json').write_text(json.dumps(workflow,indent=2),encoding='utf-8')
    history=run(workflow,out/'history.json')
    keypoints=json.loads(history['outputs']['4']['text'][0])
    (out/'keypoints.json').write_text(json.dumps(keypoints,indent=2),encoding='utf-8')
    for item in history['outputs']['3']['images']:
        with urllib.request.urlopen(URL+'/view?'+urllib.parse.urlencode(item),timeout=30) as response:
            (out/'dwpose.png').write_bytes(response.read())
    frames=keypoints if isinstance(keypoints,list) else [keypoints]
    people=[person for frame in frames for person in frame.get('people',[])]
    visible=[sum(float(c)>0 for c in p.get('pose_keypoints_2d',[])[2::3]) for p in people]
    report={'input':str(image),'people':len(people),'visible_body_keypoints':visible}
    (out/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    if len(people)!=expected_people or min(visible,default=0)<14:
        raise RuntimeError(f'Expected {expected_people} people, each with at least 14 body keypoints')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image')
    p.add_argument('--output-dir',required=True)
    p.add_argument('--people',type=int,default=1)
    args=p.parse_args()
    check(args.image,args.output_dir,args.people)
