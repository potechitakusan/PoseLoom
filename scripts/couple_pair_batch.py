"""Run kit.py pair --separation qwen-remove for every entry of a couple catalogue.

One attempt per pose: completed poses are skipped, failed or interrupted poses are
not retried unless named with --retry. The batch stops (without marking the pose)
when ComfyUI is unreachable or busy, and refuses to resume if a pose's prompt/seed
changed. Example:
  python -X utf8 scripts/couple_pair_batch.py --catalog maintenance/input/pose_themes/couple_sofa_bed/prompts.json \
      --output-dir output/couple_sofa_bed --dry-run
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'kit.py'
CONFIG = ROOT / 'kit_config.json'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save_json(path, data):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def load_catalog(path):
    catalog = json.loads(path.read_text(encoding='utf-8-sig'))
    poses = catalog['poses']
    for key in ('id', 'seed', 'prompt'):
        if len({p[key] for p in poses}) != len(poses):
            raise ValueError(f'Duplicate {key} in catalogue')
    if len(catalog['subjects']) != 2 or sorted(catalog['order']) != ['female', 'male']:
        raise ValueError('Catalogue needs two subjects and order male/female')
    return catalog


def fingerprint(catalog, pose):
    text = json.dumps([pose['prompt'], pose['seed'], catalog['steps'], catalog.get('width',1024), catalog.get('height',1024), catalog['subjects'],
                       catalog['order'], catalog['edit_seed']], ensure_ascii=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def comfy_state(url):
    """Return None when idle, otherwise a reason to stop."""
    try:
        with urllib.request.urlopen(url.rstrip('/') + '/queue', timeout=10) as response:
            queue = json.loads(response.read().decode('utf-8'))
    except Exception as error:
        return f'ComfyUI is not reachable at {url}: {error}'
    if queue.get('queue_running') or queue.get('queue_pending'):
        return 'ComfyUI queue is busy. Wait for other jobs to finish, then run the same command again.'
    return None


def pair_command(python, catalog, pose, pose_dir, female_style):
    command = [python, '-X', 'utf8', str(KIT), 'pair', '--prompt-file', str(pose_dir / 'prompt.txt'),
               '--seed', str(pose['seed']), '--steps', str(catalog['steps']), '--output-dir', str(pose_dir),
               '--width',str(catalog.get('width',1024)),'--height',str(catalog.get('height',1024)),
               '--order', *catalog['order'], '--separation', catalog['separation'],
               '--subjects', *catalog['subjects'], '--edit-seed', str(catalog['edit_seed'])]
    if female_style:
        command += ['--female-style', female_style]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--pose-id', nargs='+', help='Only these IDs, e.g. CP001 CP002')
    parser.add_argument('--limit', type=int, default=0, help='Only the first N selected poses')
    parser.add_argument('--retry', nargs='+', default=[], help='Explicitly re-run these failed/interrupted IDs')
    parser.add_argument('--female-style', choices=['anime-v2'], help='Female doll; omit for the standard doll')
    parser.add_argument('--python', default=sys.executable, help='Python with cv2 for kit.py pair')
    parser.add_argument('--timeout', type=int, default=5400, help='Seconds per pose before stopping the batch')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    catalog = load_catalog(args.catalog.resolve())
    poses = catalog['poses']
    if args.pose_id:
        wanted = {i.upper() for i in args.pose_id}
        poses = [p for p in poses if p['id'] in wanted]
        if len(poses) != len(wanted):
            raise SystemExit(f'Unknown pose ID in {sorted(wanted)}')
    if args.limit > 0:
        poses = poses[:args.limit]
    retry = {i.upper() for i in args.retry}
    out = args.output_dir.resolve()
    sys.path.insert(0, str(ROOT / 'scripts'))
    from kit_config import URL
    comfy_url = URL

    print(f'Catalogue : {args.catalog} ({catalog["library_id"]}, {len(poses)} selected)')
    print(f'Output    : {out}')
    print(f'Mode      : kit.py pair --separation {catalog["separation"]} --order {" ".join(catalog["order"])}')
    print(f'Python    : {args.python}')
    if args.dry_run:
        for pose in poses:
            print(f'  [{pose["id"]}] seed={pose["seed"]} {pose["category_ja"]} / {pose["name_ja"]}')
        print('Example command:', subprocess.list2cmdline(
            pair_command(args.python, catalog, poses[0], out / 'poses' / poses[0]['id'], args.female_style)))
        check = subprocess.run([args.python, '-c', 'import cv2, PIL, numpy'], capture_output=True, text=True)
        print('Python modules (cv2, PIL, numpy):', 'OK' if check.returncode == 0 else 'MISSING - use --python')
        print('Dry run: no ComfyUI job, no Blender, no output folder.')
        return 0 if check.returncode == 0 else 1

    out.mkdir(parents=True, exist_ok=True)
    state_path = out / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.is_file() else {
        'created_at': now(), 'catalog': str(args.catalog.resolve()), 'poses': {}}
    stop_reason = None
    for number, pose in enumerate(poses, 1):
        pid, pose_dir = pose['id'], out / 'poses' / pose['id']
        record = state['poses'].get(pid)
        label = f'[{number}/{len(poses)}] {pid} {pose["name_ja"]}'
        if record and record['fingerprint'] != fingerprint(catalog, pose):
            stop_reason = f'{pid}: prompt/seed/settings differ from the saved run. Use a new --output-dir.'
            break
        if record and record['status'] == 'succeeded':
            print(f'{label}: done, skip')
            continue
        if record and pid not in retry:
            print(f'{label}: previous status {record["status"]}, not retried (add --retry {pid} to run again)')
            continue
        stop_reason = comfy_state(comfy_url)
        if stop_reason:
            break
        pose_dir.mkdir(parents=True, exist_ok=True)
        (pose_dir / 'prompt.txt').write_text(pose['prompt'] + '\n', encoding='utf-8')
        attempts = (record or {}).get('attempts', 0) + 1
        state['poses'][pid] = {'status': 'started', 'started_at': now(), 'attempts': attempts,
                               'fingerprint': fingerprint(catalog, pose)}
        save_json(state_path, state)
        command = pair_command(args.python, catalog, pose, pose_dir, args.female_style)
        log_path = pose_dir / f'pipeline_run_{attempts}.log'
        print(f'{label}: running (log {log_path.name})', flush=True)
        with log_path.open('w', encoding='utf-8') as log:
            log.write(subprocess.list2cmdline(command) + '\n\n')
            log.flush()
            try:
                result = subprocess.run(command, cwd=ROOT / 'producer', stdout=log, stderr=subprocess.STDOUT,
                                        timeout=args.timeout)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 'timeout'
        blend = pose_dir / 'pair_posed.blend'
        succeeded = code == 0 and blend.is_file()
        state['poses'][pid].update({'status': 'succeeded' if succeeded else 'failed', 'finished_at': now(),
                                    'returncode': code, 'log': str(log_path.relative_to(out))})
        save_json(state_path, state)
        print(f'{label}: {"OK" if succeeded else f"FAILED ({code})"}', flush=True)
        if code == 'timeout':
            stop_reason = f'{pid} timed out. Check ComfyUI before running the batch again.'
            break
        if not succeeded:
            stop_reason = comfy_state(comfy_url)
            if stop_reason:
                break

    counts = {}
    for record in state['poses'].values():
        counts[record['status']] = counts.get(record['status'], 0) + 1
    summary = {'updated_at': now(), 'catalog_count': len(catalog['poses']), 'counts': counts,
               'completed': all(state['poses'].get(p['id'], {}).get('status') in ('succeeded', 'failed')
                                for p in catalog['poses']),
               'last_stop': stop_reason}
    save_json(out / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if stop_reason else 0


if __name__ == '__main__':
    sys.exit(main())
