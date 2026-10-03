"""Build a source-only GitHub/release archive; large maintenance files excluded."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile
from publication_privacy import findings

ROOT=Path(__file__).resolve().parents[1]
FOLDERS={'scripts','docs','examples','input','licenses','skills','workflows'}
FILES={'kit.py','kit_config.example.json','kit_config.12gb.example.json','AGENTS.md','README.md','README.html','.gitignore','requirements.txt','requirements-img2bvh.txt','LICENSE','LICENSE_STATUS.md'}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'releases/poseloom-agents-source.zip')
    args=parser.parse_args()
    archive=args.output.resolve()
    if archive.exists():raise FileExistsError('Choose a new archive path: '+str(archive))
    if archive.is_relative_to(ROOT/'dist'):raise ValueError('Source ZIP belongs outside the Cloudflare site')
    rows=[]
    candidates=[ROOT/name for name in FILES if (ROOT/name).is_file()]
    for folder in FOLDERS:
        if (ROOT/folder).is_dir():candidates.extend((ROOT/folder).rglob('*'))
    for path in sorted(candidates):
        rel=path.relative_to(ROOT)
        if not path.is_file() or '__pycache__' in rel.parts or path.suffix=='.pyc':continue
        if not (rel.as_posix() in FILES or rel.parts[0] in FOLDERS):continue
        if path.suffix.lower() in {'.blend','.fbx','.bvh','.pt','.safetensors','.log'}:raise ValueError(rel)
        content=path.read_text(encoding='utf-8')
        if re.search(r'[CE]:[/\\]+(?:Users|soft|sd|CodexManga)[/\\]',content,re.I):raise ValueError('Private path: '+str(rel))
        if findings(path.read_bytes(),path.suffix.lower()):raise ValueError('Publication privacy check failed: '+str(rel))
        if path.suffix=='.py':ast.parse(content,filename=str(rel))
        rows.append({'path':rel.as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest={'schema_version':1,'purpose':'source-only agent distribution','files':rows}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for row in rows:z.write(ROOT/row['path'],row['path'])
        z.write(ROOT/'manifest.json','manifest.json')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for row in rows:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
    print(json.dumps({'files':len(rows)+1,'bytes':archive.stat().st_size,'archive':str(archive)},indent=2))
if __name__=='__main__':main()
