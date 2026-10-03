"""Extract producer body presets embedded in the distributed base blends."""
import argparse
import json
from pathlib import Path
import sys
import bpy


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models-dir',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    root=args.models_dir.resolve();pending=[]
    for gender,filename in [('male','male.blend'),('female','female_anime_v2.blend')]:
        source=root/filename
        if not source.is_file():raise FileNotFoundError(source)
        bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False)
        text=bpy.data.texts.get('body_preset.json')
        if text is None:raise ValueError('No embedded body preset: '+str(source))
        value=json.loads(text.as_string())
        if not all(k in value for k in ('body_params','bone_lengths','blendshapes')):
            raise ValueError('Incomplete body preset: '+str(source))
        target=root/'sources'/f'{gender}_preset.json'
        if target.exists():
            if json.loads(target.read_text(encoding='utf-8'))!=value:
                raise FileExistsError('Existing preset differs; preserve it and choose another models directory: '+str(target))
        else:pending.append((target,value))
    for target,value in pending:
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print('MODEL_PRESETS_READY',root/'sources',flush=True)


if __name__=='__main__':main()
