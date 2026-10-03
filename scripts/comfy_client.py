"""Shared ComfyUI JSON API client and completion polling."""
import json
import time
import urllib.request
from pathlib import Path

from kit_config import ROOT, COMFY, NODE, URL, BLENDER_EXE


def request(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(URL + path, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def run(workflow, log_path, timeout=900):
    result = request('/prompt', {'prompt': workflow})
    if result.get('node_errors'):
        raise RuntimeError(result['node_errors'])
    prompt_id = result['prompt_id']
    print('Queued:', prompt_id, flush=True)
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        history = request('/history/' + prompt_id).get(prompt_id)
        if history:
            status = history.get('status', {})
            if status.get('status_str') == 'error':
                log_path.write_text(json.dumps(history, indent=2), encoding='utf-8')
                errors = [item for kind, item in status.get('messages', []) if kind == 'execution_error']
                detail = '; '.join(f"{e.get('node_type')}: {(e.get('exception_message', '') or 'Execution error').splitlines()[0]}" for e in errors)
                raise RuntimeError(f'{detail or status.get("status_str")}; full history: {log_path}')
            if status.get('completed'):
                log_path.write_text(json.dumps(history, indent=2), encoding='utf-8')
                return history
        time.sleep(2)
    raise TimeoutError(prompt_id)

