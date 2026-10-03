"""Portable maintenance checks and export jobs. No original project dependency."""
import argparse
import hashlib
import json
from pathlib import Path
from kit_config import ROOT

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,data):
    if p.exists():raise FileExistsError(p)
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('check');c.add_argument('--plan',type=Path,default=ROOT/'maintenance/release_plan.json');c.add_argument('--migration-hashes',action='store_true')
    j=sub.add_parser('jobs');j.add_argument('--plan',type=Path,default=ROOT/'maintenance/release_plan.json');j.add_argument('--ids',nargs='+',required=True);j.add_argument('--output',type=Path,required=True)
    args=p.parse_args();plan=read(args.plan);base=args.plan.resolve().parent;errors=[]
    if args.command=='jobs':
        assets={a['id']:a for a in plan['assets']}
        if set(args.ids)-assets.keys():raise ValueError('Unknown IDs')
        jobs=[{'source':str((base/assets[i]['source']).resolve()),'output':str((base/plan['export_root']/assets[i]['collection']/i).resolve()),'id':i} for i in args.ids]
        write(args.output,jobs);print(args.output);return
    for a in plan['assets']:
        for key in ('source','preview'):
            path=(base/a[key]).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():errors.append(f'{a["id"]}: missing/nonportable {key}')
        cache=base/plan['export_root']/a['collection']/a['id']
        if not (cache/'export.json').is_file():errors.append(f'{a["id"]}: missing export');continue
        export=read(cache/'export.json');source=base/a['source']
        if source.is_file() and sha(source)!=export['stamp']['source_sha256']:errors.append(f'{a["id"]}: changed source; re-export required')
        for name,h in export['sha256'].items():
            path=cache/name
            if not path.is_file() or sha(path)!=h:errors.append(f'{a["id"]}: changed export {name}')
    if args.migration_hashes:
        for entry in read(ROOT/'maintenance/manifest.json')['files']:
            path=ROOT/entry['path']
            if not path.is_file() or sha(path)!=entry['sha256']:errors.append('Migration hash: '+entry['path'])
    print(json.dumps({'assets':len(plan['assets']),'errors':errors},ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
