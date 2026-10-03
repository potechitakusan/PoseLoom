"""PoseLoom manga kit: open, infer, retarget, place and render characters."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
from kit_config import ROOT, MODELS, BLENDER_EXE, URL, ASSETS, gender, preset


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def blender(script, args, log=None):
    command = [BLENDER_EXE, '-b', '--python-exit-code', '1', '-P',
               str(ROOT/'scripts/blender'/script), '--', *map(str, args)]
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('w', encoding='utf-8') as handle:
            result = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'Blender failed ({result.returncode}): {log}\n' +
                               log.read_text(encoding='utf-8', errors='replace')[-2000:])
    else:
        subprocess.run(command, check=True)


def fresh_output(path):
    path = path.resolve()
    protected = [ASSETS, ROOT/'examples', ROOT/'scripts', ROOT/'workflows']
    if any(path == p or p in path.parents for p in protected):
        raise ValueError('Use a new output location outside the packaged assets')
    if path.exists():
        raise FileExistsError(f'Output already exists; choose a new scene/run name: {path}')
    return path


def transfer(model, fbx, output, pose_json=None):
    args = [MODELS[model], fbx.resolve(), output]
    if pose_json:
        args += ['--pose-json', pose_json.resolve()]
    blender('retarget_pose_doll.py', args, output.with_suffix('.log'))
    blender('validate_transferred_pose.py', [output], output.with_suffix('.check.log'))


def doctor(offline=False):
    report = {'blender_exe': BLENDER_EXE, 'comfy_url': URL, 'root': str(ROOT),
              'blender_exists': Path(BLENDER_EXE).is_file(),
              'models': {k: p.is_file() for k, p in MODELS.items()},
              'python_modules': {k: importlib.util.find_spec(k) is not None
                                 for k in ('PIL', 'numpy', 'cv2', 'mediapipe', 'scipy')}}
    if not offline:
        try:
            from comfy_client import request
            request('/system_stats')
            nodes = request('/object_info')
            needed = ['LoadSAM3DBodyModel', 'SAM3DBodyProcessToJson',
                      'SAM3DBodyExportRiggedFBX', 'SAM3DBodyExportPosedBVH',
                      'SAM3DBodyRenderFromPoseAndBodyPresetJson', 'DWPreprocessor']
            report['comfy_online'] = True
            report['nodes'] = {n: n in nodes for n in needed}
        except Exception as exc:
            report['comfy_online'] = False
            report['comfy_error'] = str(exc)
    report['ready_blender'] = report['blender_exists'] and all(report['models'].values())
    report['ready_pose'] = report['ready_blender'] and report.get('comfy_online', False) and all(report.get('nodes', {}).values())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def make_workflows(out):
    from run_sam3dbody import build_workflow_prompt
    from generate_qwen21_pose import build_workflow
    out.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        # Templates are reviewable API JSON; the pose command supplies upload names
        # and absolute output paths at execution time.
        data = build_workflow_prompt('UPLOAD_IMAGE.png', f'POSE_OUTPUT_{model}.bvh', 'pose',
                                     gender(model), f'POSE_OUTPUT_{model}.fbx', preset(model))
        write_json(out/f'SAM3D_{model}_api.json', data)
    prompt = (ROOT/'input/qwen21_pose_prompt.txt').read_text(encoding='utf-8')
    write_json(out/'Qwen21_generate_api.json', build_workflow(prompt))


def verify():
    manifest = json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    bad = []
    for entry in manifest['files']:
        path = ROOT/entry['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            bad.append(entry['path'])
    print(json.dumps({'checked': len(manifest['files']), 'changed_or_missing': bad}, indent=2))
    return 1 if bad else 0


def main():
    # Pass the advanced commands through without changing cwd or hiding flags.
    if len(sys.argv) > 1 and sys.argv[1] in ('pair', 'generate', 'img2bvh', 'batch', 'catalog', 'privacy'):
        targets = {'pair': 'run_pair_pose_pipeline.py', 'generate': 'generate_qwen21_pose.py',
                   'img2bvh': 'img2bvh/main.py', 'batch': 'female_v2_pose_batch.py', 'catalog': 'build_catalog.py',
                   'privacy': 'publication_privacy.py'}
        argv = sys.argv[2:]
        if sys.argv[1] == 'img2bvh' and not any(a in ('--model', '-m') or a.startswith('--model=') for a in argv):
            argv += ['--model', str(ROOT/'assets/pose_landmarker_heavy.task')]
        return subprocess.call([sys.executable, '-X', 'utf8', str(ROOT/'scripts'/targets[sys.argv[1]]), *argv])
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    d = sub.add_parser('doctor', help='Read-only environment check'); d.add_argument('--offline', action='store_true')
    o = sub.add_parser('open', help='Open a model or saved scene with the sidebar')
    o.add_argument('target', help='male, female-v2, or a .blend path')
    s = sub.add_parser('pose', help='Image -> SAM3D -> editable doll')
    s.add_argument('--image', type=Path, required=True)
    s.add_argument('--model', choices=MODELS, default='female-v2')
    s.add_argument('--output-dir', type=Path, required=True)
    s.add_argument('--mask', type=Path)
    s.add_argument('--timeout', type=int, default=900)
    r = sub.add_parser('retarget', help='Reuse an already exported matching SAM3D FBX')
    r.add_argument('--fbx', type=Path, required=True)
    r.add_argument('--model', choices=MODELS, default='female-v2')
    r.add_argument('--output', type=Path, required=True)
    r.add_argument('--pose-json', type=Path)
    e = sub.add_parser('export', help='Saved blend -> BVH and editable blend with embedded metadata')
    e.add_argument('--blend',type=Path,required=True)
    e.add_argument('--output-dir',type=Path,required=True)
    e.add_argument('--id',required=True)
    s = sub.add_parser('scene', help='Append characters to a background and render')
    s.add_argument('--spec', type=Path, required=True)
    s.add_argument('--output', type=Path, required=True)
    s.add_argument('--no-render', action='store_true')
    w = sub.add_parser('workflows', help='Write API templates using current settings')
    w.add_argument('--output-dir', type=Path, default=ROOT/'workflows')
    sub.add_parser('verify', help='Check the packaged file checksums')
    sub.add_parser('prepare-models', help='Extract body presets from the distributed base blends')
    for name in ('pair', 'generate', 'img2bvh', 'batch', 'catalog', 'privacy'):
        sub.add_parser(name, help=f'Run {name}; see kit.py {name} --help')
    args = p.parse_args()
    if args.command == 'doctor':
        result = doctor(args.offline)
        return 0 if result['ready_blender' if args.offline else 'ready_pose'] else 1
    if args.command == 'open':
        target = MODELS.get(args.target, Path(args.target).resolve())
        if not target.is_file():
            raise FileNotFoundError(target)
        return subprocess.call([BLENDER_EXE, str(target), '--python', str(ROOT/'scripts/blender/pose_doll_tools.py')])
    if args.command == 'pose':
        from run_sam3dbody import process_image
        image = args.image.resolve()
        if not image.is_file():
            raise FileNotFoundError(image)
        out = fresh_output(args.output_dir)
        paths = process_image(image, out/'analysis', gender(args.model), True,
                              preset(args.model), args.timeout, args.mask)
        transfer(args.model, paths['fbx'], out/'posed.blend', paths['pose'])
        write_json(out/'result.json', {'model': args.model, 'input': str(image),
                                     'blend': 'posed.blend', 'render': 'posed.png',
                                     'openpose': 'posed_openpose.png', 'keypoints': 'posed_openpose.json'})
        print('COMPLETE', out/'result.json')
    elif args.command == 'retarget':
        output = fresh_output(args.output)
        if output.suffix.lower() != '.blend':
            raise ValueError('--output must end in .blend')
        transfer(args.model, args.fbx, output, args.pose_json)
        print('COMPLETE', output)
    elif args.command == 'export':
        output = fresh_output(args.output_dir)
        blender('export_asset.py', ['--blend',args.blend.resolve(),'--output-dir',output,'--id',args.id])
        print('COMPLETE',output)
    elif args.command == 'scene':
        output = fresh_output(args.output)
        if output.suffix.lower() != '.blend':
            raise ValueError('--output must end in .blend')
        values = ['--spec', args.spec.resolve(), '--output', output]
        if args.no_render:
            values += ['--no-render']
        blender('stage_scene.py', values, output.with_suffix('.log'))
        print('COMPLETE', output)
    elif args.command == 'workflows':
        make_workflows(args.output_dir.resolve())
    elif args.command == 'verify':
        return verify()
    elif args.command == 'prepare-models':
        blender('prepare_models.py',['--models-dir',ASSETS])
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
