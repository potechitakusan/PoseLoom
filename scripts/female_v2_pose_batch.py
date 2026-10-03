"""One attempt per candidate: all Qwen images first, then SAM3D and Blender renders.

No OpenAI API calls. No extra Blender editing tests. Release requires explicit
visual review decisions and operates on saved files without launching Blender.
"""
import argparse
from collections import Counter
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from kit_config import ROOT, CONFIG, MODELS, BLENDER_EXE, URL, preset

CATALOG = ROOT/'examples/batch.example.json'
TERMINAL = {'succeeded', 'failed', 'abandoned'}
CHECKS = {'existing_six_presets': 'previously_tested',
          'new_pose_blender_editing_test': 'not_run_by_user_request',
          'new_pose_visual_review': 'pending'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temp, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def load_catalog(path):
    data = read_json(path)
    rows = data['poses']
    if data.get('schema_version', 1) == 1:
        if len(rows) != 100 or [r['id'] for r in rows] != [f'F{i:03d}' for i in range(1,101)]:
            raise ValueError('Catalogue must contain F001..F100 in order')
    elif data['schema_version'] == 2:
        if not rows or data['candidate_count'] != len(rows) or data['model'] != 'female-v2':
            raise ValueError('Invalid candidate count or model')
        if not re.fullmatch(r'[a-z][a-z0-9_]*', data['library_id']):
            raise ValueError('Invalid library ID')
        if len({r['id'] for r in rows}) != len(rows) or any(not re.fullmatch(r'[A-Z]{1,4}[0-9]{3}', r['id']) for r in rows):
            raise ValueError('Invalid or duplicate pose IDs')
        if data.get('retry_policy') != 'never':
            raise ValueError('Only retry_policy=never is supported')
    else:
        raise ValueError('Unsupported catalogue schema')
    if len({r['prompt'] for r in rows}) != len(rows) or len({r['seed'] for r in rows}) != len(rows):
        raise ValueError('Prompts and seeds must be distinct')
    for row in rows:
        if any(row[k] < 64 or row[k] % 8 for k in ('width','height')):
            raise ValueError(f'Invalid image dimensions: {row["id"]}')
    return data


def contract(catalog):
    from kit_config import CONFIG_DIR
    template_hashes = {k:digest(CONFIG_DIR/CONFIG[k]) for k in ('generation_workflow','edit_workflow') if CONFIG.get(k)}
    return {'workflow_template_sha256':template_hashes, 'catalog_sha256': digest(catalog), 'model_sha256': digest(MODELS['female-v2']),
            'body_preset_sha256': digest(preset('female-v2')), 'config': CONFIG,
            'comfy_url': URL, 'blender_exe': BLENDER_EXE,
            'pipeline_sha256': {str(p.relative_to(ROOT)): digest(p) for p in
                [ROOT/'scripts/generate_qwen21_pose.py', ROOT/'scripts/run_sam3dbody.py',
                 ROOT/'scripts/blender/retarget_pose_doll.py']}}


def new_state(catalog, signature):
    return {'schema_version':1, 'created_at':now(), 'contract':signature,
            'retry_policy':'never', 'validation':CHECKS,
            'poses':[{**r, 'status':'pending', 'generation_attempts':0, 'pose_attempts':0,
                      'files':{}, 'error':None} for r in catalog['poses']]}


def abandon_interrupted(state):
    for row in state['poses']:
        if row['status'] in ('generating','processing'):
            row.update(status='abandoned', error='Interrupted attempt; deliberately not retried', finished_at=now())


def save_state(out, state):
    state['updated_at'] = now()
    write_json(out/'state.json', state)
    counts = Counter(r['status'] for r in state['poses'])
    complete = all(r['status'] in TERMINAL for r in state['poses'])
    summary = {'updated_at':state['updated_at'], 'completed':complete,
               'counts':dict(counts), 'candidate_count':len(state['poses']), 'retry_policy':'never',
               'validation':CHECKS, 'last_stop':state.get('last_stop'),
               'next_step':'Build the catalog; visual selection is optional and follows the user request' if complete else 'Run the same batch command to process only unattempted stages',
               'results':[{'id':r['id'],'name_ja':r['name_ja'],'status':r['status'],
                           'error':r.get('error'),'files':r['files']} for r in state['poses']]}
    write_json(out/'summary.json', summary)


@contextmanager
def batch_lock(out):
    # A held OS lock, not a stale marker: forcibly closing PowerShell releases it.
    handle = (out/'run.lock').open('a+b')
    handle.seek(0); handle.write(b'0'); handle.flush(); handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('This batch is already running')
    try:
        yield
    finally:
        handle.close()


def ensure_idle():
    from comfy_client import request
    queue = request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):
        raise RuntimeError('ComfyUI queue is busy. Wait for it to finish before resuming this batch.')


class BatchStop(RuntimeError):
    """Unknown server state: stop submitting new work, never resubmit the attempt."""


def tracked_run(workflow, log_path, timeout=900):
    from comfy_client import request
    # Keep the prompt id immediately, including when inference fails or times out.
    queued = request('/prompt', {'prompt':workflow})
    if queued.get('node_errors'):
        raise RuntimeError(str(queued['node_errors']))
    prompt_id = queued['prompt_id']
    write_json(log_path.with_name(log_path.stem+'_job.json'), {'prompt_id':prompt_id, 'submitted_at':now()})
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        history = request('/history/'+prompt_id).get(prompt_id)
        if history:
            status = history.get('status', {})
            if status.get('status_str') == 'error':
                write_json(log_path, history)
                errors = [d.get('exception_message','') for kind,d in status.get('messages',[]) if kind=='execution_error']
                raise RuntimeError('; '.join(errors) or 'ComfyUI inference failed')
            if status.get('completed'):
                write_json(log_path, history)
                return history
        time.sleep(2)
    # Do not cancel global work or pile more jobs onto an uncertain queue.
    raise BatchStop(f'Timed out: prompt {prompt_id}. No retry. Check ComfyUI before resuming.')


def preflight(needs_generation=True):
    from comfy_client import request
    if not Path(BLENDER_EXE).is_file():
        raise FileNotFoundError(BLENDER_EXE)
    for path in (MODELS['female-v2'], preset('female-v2')):
        if not path.is_file(): raise FileNotFoundError(path)
    from PIL import Image  # Needed later to check PNGs and make contact sheets.
    nodes = request('/object_info')
    needed = ['LoadImage','PreviewAny','PreviewImage','LoadSAM3DBodyModel',
              'SAM3DBodyProcessToJson','SAM3DBodyExportRiggedFBX','SAM3DBodyExportPosedBVH',
              'SAM3DBodyRenderFromPoseAndBodyPresetJson']
    missing = [n for n in needed if n not in nodes]
    if missing: raise RuntimeError('Missing ComfyUI nodes: '+', '.join(missing))
    if needs_generation:
        from generate_qwen21_pose import build_workflow
        from workflow_template import validate
        errors = validate(build_workflow('preflight'),nodes)
        if errors:raise RuntimeError('Generation workflow: '+'; '.join(errors))
    ensure_idle()


def generate_one(row, catalog, folder, timeout):
    from generate_qwen21_pose import build_workflow
    workflow = build_workflow(row['prompt'],row['seed'],catalog['steps'],row['width'],row['height'],catalog['negative_prompt'])
    library_id = catalog.get('library_id', 'female_v2_100')
    workflow['9']['inputs']['filename_prefix'] = f'PoseLoom/{library_id}/{row["id"]}_{row["seed"]}'
    write_json(folder/'generation_workflow_api.json', workflow)
    (folder/'prompt.txt').write_text(row['prompt']+'\n',encoding='utf-8')
    history = tracked_run(workflow, folder/'generation_history.json', timeout)
    images = history.get('outputs',{}).get('9',{}).get('images',[])
    if len(images)!=1: raise RuntimeError(f'Expected one image, got {len(images)}')
    with urllib.request.urlopen(URL+'/view?'+urllib.parse.urlencode(images[0]), timeout=60) as response:
        (folder/'source.png').write_bytes(response.read())
    from PIL import Image
    with Image.open(folder/'source.png') as im: im.verify()


def pose_one(row, folder, sam_timeout, blender_timeout):
    from run_sam3dbody import process_image
    paths = process_image(folder/'source.png', folder/'analysis', 'female', True, preset('female-v2'),
                          sam_timeout, workflow_runner=tracked_run)
    # Direct conversion and preview only: deliberately bypass kit.transfer(),
    # which otherwise launches validate_transferred_pose.py as an extra process.
    command = [BLENDER_EXE, '-b', '--python-exit-code', '1', '-P',
               str(ROOT/'scripts/blender/retarget_pose_doll.py'), '--', str(MODELS['female-v2']),
               str(paths['fbx']), str(folder/'posed.blend'), '--pose-json', str(paths['pose']),
               '--pose-id', row['id'], '--pose-label', row['name_ja'], '--portable-output']
    with (folder/'blender.log').open('w',encoding='utf-8') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=blender_timeout)
    if result.returncode:
        raise RuntimeError(f'Blender conversion/render failed ({result.returncode}); see blender.log')
    for name in ('posed.blend','posed.png','posed_openpose.png','posed_openpose.json'):
        if not (folder/name).is_file() or (folder/name).stat().st_size < 100:
            raise RuntimeError('Missing output: '+name)
    from PIL import Image
    with Image.open(folder/'posed.png') as im: im.verify()
    return {name:digest(folder/name) for name in ('posed.blend','posed.png','posed_openpose.png','posed_openpose.json')}


def execute_stage(out, state, catalog, stage, args):
    waiting, active, attempt = ('pending','generating','generation_attempts') if stage=='generate' else ('generated','processing','pose_attempts')
    for row in state['poses']:
        if row['status'] != waiting: continue
        # Infrastructure checks happen before consuming the one attempt.
        ensure_idle()
        folder = out/'poses'/row['id']
        folder.mkdir(parents=True,exist_ok=True)
        if row[attempt]: raise RuntimeError('Refusing a second attempt: '+row['id'])
        row.update(status=active, started_at=now(), stage=stage)
        row[attempt] = 1
        save_state(out,state)
        print(f"[{row['id']} / {len(state['poses'])} candidates] {stage}: {row['name_ja']}",flush=True)
        stop = None
        try:
            with (folder/f'{stage}.log').open('w',encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
                if stage=='generate':
                    generate_one(row,catalog,folder,args.generation_timeout)
                    row.update(status='generated',source_sha256=digest(folder/'source.png'))
                    row['files']['source'] = f"poses/{row['id']}/source.png"
                else:
                    if digest(folder/'source.png') != row['source_sha256']:
                        raise RuntimeError('Generated source image was modified')
                    row['output_sha256'] = pose_one(row,folder,args.sam_timeout,args.blender_timeout)
                    row['status']='succeeded'
                    row['files'].update({key:f"poses/{row['id']}/{name}" for key,name in
                        [('blend','posed.blend'),('preview','posed.png'),('openpose','posed_openpose.png'),('keypoints','posed_openpose.json')]})
        except KeyboardInterrupt:
            row.update(status='abandoned',error='Interrupted by user; not retried')
            stop=KeyboardInterrupt()
        except Exception as exc:
            row.update(status='failed',error=f'{type(exc).__name__}: {exc}')
            if isinstance(exc,(BatchStop,urllib.error.URLError,TimeoutError,ConnectionError)):
                stop=exc
        finally:
            row['finished_at']=now()
            save_state(out,state)
        print(f"  {row['status']}"+(f": {row['error']}" if row.get('error') else ''),flush=True)
        if stop: raise stop


def run_batch(args):
    catalog=load_catalog(args.catalog)
    signature=contract(args.catalog)
    if catalog.get('schema_version') == 2:
        signature['batch_runner_sha256'] = digest(Path(__file__))
    out=args.output_dir.resolve()
    if args.dry_run:
        print(json.dumps({'mode':'dry_run_no_jobs', 'candidates':len(catalog['poses']), 'categories':dict(Counter(r['category_ja'] for r in catalog['poses'])),
                          'output':str(out),'phases':['generate_all','sam3d_and_blender'],
                          'additional_blender_tests':False,'retry_policy':'never'},ensure_ascii=False,indent=2))
        return 0
    if out.exists() and any(out.iterdir()) and not (out/'state.json').is_file():
        raise ValueError('Non-empty output folder has no batch state; use a new directory')
    out.mkdir(parents=True,exist_ok=True)
    with batch_lock(out):
        if (out/'state.json').is_file():
            state=read_json(out/'state.json')
            if state['contract'] != signature:
                raise ValueError('Catalogue/model/pipeline/settings changed. Restore them before resuming this batch.')
        else:
            state=new_state(catalog,signature)
            write_json(out/'catalog_snapshot.json',catalog)
            save_state(out,state)
        abandon_interrupted(state)
        save_state(out,state)
        if all(r['status'] in TERMINAL for r in state['poses']):
            print('Already completed; no jobs rerun. See',out/'summary.json')
            return 0
        try:
            preflight(needs_generation=any(r['status']=='pending' for r in state['poses']))
            state.pop('last_stop',None)
            execute_stage(out,state,catalog,'generate',args)
            execute_stage(out,state,catalog,'pose',args)
        except BaseException as exc:
            state['last_stop']={'at':now(),'message':f'{type(exc).__name__}: {exc}'}
            save_state(out,state)
            raise
        save_state(out,state)
    print('Batch complete:',dict(Counter(r['status'] for r in state['poses'])),flush=True)
    print('Tell Codex the batch directory:',out,flush=True)
    return 0


def import_sources(args):
    """Start a new batch from saved reference images, preserving the old run."""
    catalog=load_catalog(args.catalog)
    out=args.output_dir.resolve(); source=args.images_root.resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory; existing runs are preserved')
    old_state=source.parent/'state.json'
    old_rows={r['id']:r for r in read_json(old_state)['poses']} if old_state.is_file() else {}
    images=[]
    for row in catalog['poses']:
        path=source/row['id']/'source.png'
        if not path.is_file():raise FileNotFoundError(path)
        actual=digest(path)
        previous=old_rows.get(row['id'])
        if previous:
            if previous['prompt']!=row['prompt'] or previous['seed']!=row['seed']:
                raise ValueError('Image prompt/seed differs: '+row['id'])
            if previous.get('source_sha256')!=actual:
                raise ValueError('Source image hash differs: '+row['id'])
        from PIL import Image
        with Image.open(path) as image:image.verify()
        images.append((row['id'],path,actual,previous))
    signature=contract(args.catalog)
    if catalog.get('schema_version')==2:signature['batch_runner_sha256']=digest(Path(__file__))
    out.mkdir(parents=True)
    with batch_lock(out):
        state=new_state(catalog,signature)
        state['imported_from']={'images_root':str(source),'state_sha256':digest(old_state) if old_state.is_file() else None}
        for row,(_,path,actual,previous) in zip(state['poses'],images):
            folder=out/'poses'/row['id'];folder.mkdir(parents=True)
            shutil.copy2(path,folder/'source.png')
            row.update(status='generated',source_sha256=actual,
                       source_reused=True,previous_status=previous.get('status') if previous else None,
                       previous_pose_attempts=previous.get('pose_attempts',0) if previous else 0)
            row['files']['source']=f"poses/{row['id']}/source.png"
        write_json(out/'catalog_snapshot.json',catalog)
        save_state(out,state)
    print('Imported',len(images),'verified reference images; no inference has run.',flush=True)
    return 0


def font(size):
    from PIL import ImageFont
    for path in ('C:/Windows/Fonts/YuGothM.ttc','C:/Windows/Fonts/meiryo.ttc','C:/Windows/Fonts/arial.ttf'):
        if Path(path).exists():return ImageFont.truetype(path,size)
    return ImageFont.load_default(size=size)


def contact_sheets(items, destination, title):
    """Exactly six slots per page; no inference and no Blender process."""
    from PIL import Image, ImageDraw, ImageOps
    destination.mkdir(parents=True,exist_ok=True)
    pages=[]
    for start in range(0,len(items),6):
        selected=items[start:start+6]
        canvas=Image.new('RGB',(1200,1160),'#f1f3f5')
        draw=ImageDraw.Draw(canvas)
        page=len(pages)+1
        draw.text((18,10),f'{title} / {page:02d}',font=font(23),fill='#20313c')
        ids=[]
        for index,(row,path) in enumerate(selected):
            x=(index%3)*400; y=48+(index//3)*552
            with Image.open(path) as im:
                picture=ImageOps.contain(im.convert('RGB'),(388,488))
            canvas.paste(picture,(x+(400-picture.width)//2,y+(488-picture.height)//2))
            draw.text((x+10,y+493),f"{row['id']}  {row['name_ja']}",font=font(20),fill='#182b38')
            draw.text((x+10,y+520),row['category_ja'],font=font(16),fill='#596879')
            ids.append(row['id'])
        name=f'contact_{page:02d}.jpg'
        canvas.save(destination/name,quality=90)
        pages.append({'file':name,'ids':ids})
    write_json(destination/'pages.json',pages)
    return pages


def completed_state(out):
    state=read_json(out/'state.json')
    if not all(r['status'] in TERMINAL for r in state['poses']):
        raise ValueError('Batch is not complete. Resume batch run first.')
    return state


def checked_artifact(out,row,key):
    path=(out/row['files'][key]).resolve()
    if out.resolve() not in path.parents:
        raise ValueError('Artifact path escapes batch directory')
    expected=row.get('output_sha256',{}).get(path.name)
    if not expected or digest(path)!=expected:
        raise ValueError(f'Artifact was modified or is missing: {row["id"]} {key}')
    return path


def review(out):
    state=completed_state(out)
    selected=[r for r in state['poses'] if r['status']=='succeeded']
    items=[(r,checked_artifact(out,r,'preview')) for r in selected]
    folder=out/'review'
    pages=contact_sheets(items,folder,'女性v2 / 選別前・動作テスト省略')
    decisions=folder/'decisions.json'
    if not decisions.exists():
        write_json(decisions,{'schema_version':1,'batch_contract':state['contract'],
                              'criteria':'Exclude obvious visible breakage; no extra Blender testing',
                              'poses':{r['id']:{'decision':'pending','reason':''} for r in selected}})
    write_json(folder/'review_index.json',{'pages':pages,'candidate_count':len(selected),
                                         'decisions':'decisions.json','batch_summary':'../summary.json'})
    print('Review',len(selected),'successful candidates on',len(pages),'sheets:',folder)


def release(out, destination):
    """Only explicit accept decisions are published; original results are retained."""
    state=completed_state(out)
    decisions=read_json(out/'review/decisions.json')
    if decisions['batch_contract']!=state['contract']:raise ValueError('Review belongs to another batch')
    successful={r['id']:r for r in state['poses'] if r['status']=='succeeded'}
    if set(decisions['poses'])!=set(successful):raise ValueError('Review must cover exactly the successful candidates')
    for ident,d in decisions['poses'].items():
        if d['decision'] not in ('accept','exclude'):raise ValueError(f'Unreviewed candidate: {ident}')
        if d['decision']=='exclude' and not d.get('reason','').strip():raise ValueError('Record an exclusion reason: '+ident)
    accepted=[r for r in state['poses'] if r['status']=='succeeded' and decisions['poses'][r['id']]['decision']=='accept']
    if not accepted:raise ValueError('No accepted poses to release')
    if destination.exists():raise FileExistsError('Use a new release directory; existing release is preserved')
    artifacts={r['id']:{k:checked_artifact(out,r,k) for k in ('blend','preview','openpose','keypoints')} for r in accepted}
    final_destination=destination
    destination=destination.with_name(destination.name+'.building')
    if destination.exists():raise FileExistsError('An unfinished release staging directory exists: '+str(destination))
    destination.mkdir(parents=True)
    catalogue=[]
    for row in accepted:
        folder=destination/'poses'/row['id']; folder.mkdir(parents=True)
        paths={}
        for key,source in artifacts[row['id']].items():
            target=folder/source.name; shutil.copy2(source,target)
            paths[key]=target.relative_to(destination).as_posix()
        entry={k:row[k] for k in ('id','slug','name_ja','category','category_ja','support_note','seed','prompt')}
        entry.update(files=paths,validation={**CHECKS,'new_pose_visual_review':'accepted_from_contact_sheet'},
                     review_reason=decisions['poses'][row['id']].get('reason',''))
        catalogue.append(entry)
        write_json(folder/'pose.json',entry)
    pages=contact_sheets([(r,destination/r['files']['preview']) for r in catalogue],destination/'contact_sheets','女性v2 / 採用ポーズ・動作テスト省略')
    write_json(destination/'catalog.json',{'model':'female-v2','candidate_count':len(state['poses']),'accepted_count':len(catalogue),
                                         'poses':catalogue,'contact_sheets':pages,
                                         'validation':{**CHECKS,'new_pose_visual_review':'accepted_from_contact_sheet'},
                                         'note':'Pose names describe the intended prompt; inference may differ.'})
    write_json(destination/'review_decisions.json',decisions)
    excluded=[{'id':r['id'],'status':r['status'],'reason':r.get('error') or decisions['poses'].get(r['id'],{}).get('reason','')}
              for r in state['poses'] if r['status']!='succeeded' or decisions['poses'][r['id']]['decision']=='exclude']
    write_json(destination/'excluded.json',excluded)
    pictures=''.join(f'<figure><img src="contact_sheets/{p["file"]}" alt="{html.escape(", ".join(p["ids"]))}"><figcaption>{html.escape(", ".join(p["ids"]))}</figcaption></figure>' for p in pages)
    links=''.join(f'<tr><td>{r["id"]}</td><td>{html.escape(r["name_ja"])}</td><td>{html.escape(r["category_ja"])}</td><td><a href="{r["files"]["blend"]}">blend</a> · <a href="{r["files"]["preview"]}">PNG</a></td></tr>' for r in catalogue)
    (destination/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>女性v2 ポーズ集</title><style>body{max-width:1200px;margin:30px auto;font-family:Meiryo,sans-serif}img{max-width:100%}figure{margin:20px 0}td{padding:7px 16px;border-bottom:1px solid #ddd}</style>'+f'<h1>女性v2 ポーズ集：{len(catalogue)}件</h1><p>6ポーズずつの目視選別済み。新規ポーズの追加Blender動作テストは省略しています。</p>'+pictures+'<table>'+links+'</table>',encoding='utf-8')
    files=[{'path':p.relative_to(destination).as_posix(),'sha256':digest(p)} for p in sorted(destination.rglob('*')) if p.is_file()]
    write_json(destination/'checksums.json',files)
    destination.rename(final_destination)
    print('Released',len(catalogue),'poses to',final_destination)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('run')
    run.add_argument('--catalog',type=Path,default=CATALOG)
    run.add_argument('--output-dir',type=Path,required=True)
    run.add_argument('--dry-run',action='store_true')
    run.add_argument('--generation-timeout',type=int,default=1800)
    run.add_argument('--sam-timeout',type=int,default=900)
    run.add_argument('--blender-timeout',type=int,default=600)
    imported=sub.add_parser('import-sources',help='Prepare a new run from existing <ID>/source.png images')
    imported.add_argument('--catalog',type=Path,required=True)
    imported.add_argument('--images-root',type=Path,required=True)
    imported.add_argument('--output-dir',type=Path,required=True)
    for name in ('review','release'):
        p=sub.add_parser(name);p.add_argument('--output-dir',type=Path,required=True)
        if name=='release':p.add_argument('--destination',type=Path,default=ROOT/'output/reviewed_release')
    args=parser.parse_args()
    if args.command=='import-sources':return import_sources(args)
    if args.command=='run':
        if min(args.generation_timeout,args.sam_timeout,args.blender_timeout)<=0:parser.error('Timeouts must be positive')
        return run_batch(args)
    if args.command=='review':review(args.output_dir.resolve())
    if args.command=='release':release(args.output_dir.resolve(),args.destination.resolve())
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except KeyboardInterrupt:
        print('Stopped. Interrupted attempts are not retried; rerun to continue untouched entries.',file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f'ERROR: {type(exc).__name__}: {exc}',file=sys.stderr)
        sys.exit(1)
