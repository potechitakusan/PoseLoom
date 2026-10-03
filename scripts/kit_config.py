"""Distribution settings, resolved independently of the current directory."""
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config_path = Path(os.environ.get('POSELOOM_CONFIG', str(ROOT / 'kit_config.json'))).resolve()
if not config_path.is_file():
    config_path = ROOT / 'kit_config.example.json'
CONFIG = json.loads(config_path.read_text(encoding='utf-8-sig'))
CONFIG_DIR = config_path.parent
blender_value = os.environ.get('POSELOOM_BLENDER', CONFIG['blender_exe'])
BLENDER_EXE = shutil.which(blender_value) or blender_value
URL = os.environ.get('POSELOOM_COMFY_URL', CONFIG['comfy_url']).rstrip('/')
COMFY = Path(os.environ.get('POSELOOM_COMFY_ROOT', CONFIG['comfy_root']))
if not COMFY.is_absolute():
    COMFY = (CONFIG_DIR / COMFY).resolve()
NODE = COMFY / 'custom_nodes/ComfyUI-SAM3DBody_utills'
ASSETS = Path(os.environ.get('POSELOOM_ASSET_ROOT', CONFIG.get('asset_root', 'assets/models')))
if not ASSETS.is_absolute():
    ASSETS = (config_path.parent / ASSETS).resolve()
MODELS = {'male': ASSETS/'male.blend',
          'female': ASSETS/'female_anime_v2.blend',
          'female-v2': ASSETS/'female_anime_v2.blend'}


def gender(model):
    return 'male' if model == 'male' else 'female'


def preset(model):
    return ASSETS / f'sources/{gender(model)}_preset.json'
