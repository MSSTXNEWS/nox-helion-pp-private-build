#!/usr/bin/env python3
"""NOX 9B stage registry: zero-copy 32-layer verification, NOT a model trainer.

Never modifies model weights, old checkpoints, or S03. Makes a resumable,
receipt-compatible execution plan for a future supported GPU trainer.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT_DEFAULT = Path(r'C:\NOX_HELION\NOX_NEW\brain\prime')
LAYER = re.compile(r'(?:^|\.)(?:language_model|text_model|model)\.layers\.(\d+)\.')
EXPECTED_LAYERS = 32
STAGE_COUNT = 8


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as temp:
        temp.write(content)
        name = temp.name
    os.replace(name, path)
    if path.name == 'NOX_9B_SEGMENT_PLAN.json':
        render_progress(path.with_name('NOX_9B_SEGMENT_PROGRESS.html'), data)


def render_progress(path, plan):
    """Render an offline report from real, serialized state only."""
    from html import escape
    cells = []
    for s in plan['stages']:
        cells.append(
            '<article><div class="num">' + escape(s['segment_id']) + '</div>'
            '<div class="layers">Layers %s–%s</div>' % (s['layers'][0] + 1, s['layers'][-1] + 1)
            + '<div class="status">' + escape(s['status']) + '</div>'
            + '<div class="count">Tensor index entries: ' + str(s['tensor_count']) + '</div></article>'
        )
    import base64
    template = base64.b64decode(
        'PCFkb2N0eXBlIGh0bWw+PGh0bWwgbGFuZz0icnUiPjxoZWFkPjxtZXRhIGNoYXJzZXQ9InV0Zi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEiPgo8bWV0YSBodHRwLWVxdWl2PSJyZWZyZXNoIiBjb250ZW50PSIzMCI+Cjx0aXRsZT5OT1ggUFJJTUUgwrcg0YHQtdCz0LzQtdC90YLQvdGL0Lkg0LrQvtC90YLRgNC+0LvRjDwvdGl0bGU+PHN0eWxlPgo6cm9vdHtjb2xvci1zY2hlbWU6ZGFya30qe2JveC1zaXppbmc6Ym9yZGVyLWJveH1ib2R5e21hcmdpbjowO2JhY2tncm91bmQ6cmFkaWFsLWdyYWRpZW50KGNpcmNsZSBhdCA2MCUgLTMwJSwjM2UzMTE5LCMxMTEyMTEgNjAlLCMwODA5MDkpO2NvbG9yOiNlZWU4ZGY7Zm9udDoxNXB4IHN5c3RlbS11aSxBcmlhbH0KbWFpbnttYXgtd2lkdGg6MTA0MHB4O21hcmdpbjphdXRvO3BhZGRpbmc6MzVweCAyMnB4IDcwcHh9LmV5ZWJyb3d7Y29sb3I6I2Q3YjA3Mztmb250LXNpemU6MTJweDtsZXR0ZXItc3BhY2luZzouMjRlbX0KaDF7Zm9udC13ZWlnaHQ6NTAwO2xldHRlci1zcGFjaW5nOi4xZW07Zm9udC1zaXplOjI4cHh9LnN0YXR1c2Jhcntib3JkZXI6MXB4IHNvbGlkICM1MDQzMzI7Ym9yZGVyLXJhZGl1czoxMnB4O3BhZGRpbmc6MTNweDtjb2xvcjojZGZjMjkwO292ZXJmbG93LXdyYXA6YW55d2hlcmV9LnRvdGFse2ZvbnQtc2l6ZTo1MnB4O2NvbG9yOiNlOGJlNzU7bWFyZ2luLXRvcDoyNHB4fS5oaW50e2NvbG9yOiNiNWFiOWU7Zm9udC1zaXplOjEycHh9Ci5ncmlke21hcmdpbi10b3A6MjNweDtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCg0LDFmcik7Z2FwOjEycHh9YXJ0aWNsZXttaW4taGVpZ2h0OjE0N3B4O3BhZGRpbmc6MThweDtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCgxNDBkZWcsIzI5MjQxYiwjMTExNTE1KTtib3JkZXI6MXB4IHNvbGlkICM0ODQwMmU7Ym9yZGVyLXJhZGl1czoxNHB4fQoubnVte2ZvbnQtc2l6ZToyMnB4O2NvbG9yOiNlM2JhNzB9LmxheWVyc3ttYXJnaW4tdG9wOjZweDtjb2xvcjojYzViOGEyO2ZvbnQtc2l6ZToxM3B4fS5zdGF0dXN7Y29sb3I6I2UyYTc2Mztmb250LXNpemU6MTJweDttYXJnaW4tdG9wOjIxcHh9LmNvdW50e2ZvbnQtc2l6ZToxMXB4O2NvbG9yOiM5NjkzOTA7bWFyZ2luLXRvcDo2cHh9CmZvb3Rlcntib3JkZXItdG9wOjFweCBzb2xpZCAjNTQ0NDJlO21hcmdpbi10b3A6MzZweDtwYWRkaW5nLXRvcDoyMnB4O2NvbG9yOiNhYWEyOTg7Zm9udC1zaXplOjEzcHg7bGluZS1oZWlnaHQ6MS44O292ZXJmbG93LXdyYXA6YW55d2hlcmV9QG1lZGlhKG1heC13aWR0aDo3MjBweCl7LmdyaWR7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgyLDFmcil9fQo8L3N0eWxlPjwvaGVhZD48Ym9keT48bWFpbj48ZGl2IGNsYXNzPSJleWVicm93Ij5OT1ggSEVMSU9OIMK3IEZPUkdFPC9kaXY+CjxoMT7QodCV0JPQnNCV0J3QotCrIDlCIC8gTk8tTE9TUzwvaDE+PGRpdiBjbGFzcz0ic3RhdHVzYmFyIj7QodC+0YHRgtC+0Y/QvdC40LU6IHtzdGF0dXN9PC9kaXY+CjxkaXYgY2xhc3M9InRvdGFsIj57ZG9uZX0gLyA4PC9kaXY+PGRpdiBjbGFzcz0iaGludCI+0KTQuNC30LjRh9C10YHQutC4INC/0YDQvtCy0LXRgNC10L3QvdGL0YUg0L7QsdGD0YfQtdC90L3Ri9GFINGB0LXQs9C80LXQvdGC0L7Qsi4g0J3QtSDCq9C/0YDQvtGG0LXQvdGCINC40L3RgtC10LvQu9C10LrRgtCwwrsuPC9kaXY+CjxkaXYgY2xhc3M9ImdyaWQiPntjZWxsc308L2Rpdj48Zm9vdGVyPtCf0L7Qu9C90YvQuSDQvdCw0LHQvtGAIDlCLdCy0LXRgdC+0LI6IHtpbmhlcml0ZWR9LiDQmNGB0YXQvtC00L3Ri9C1INCy0LXRgdCwINGB0L7RhdGA0LDQvdGP0Y7RgtGB0Y8g0LHQtdC3INC40LfQvNC10L3QtdC90LjRjy48YnI+CtCg0LXQsNC70YzQvdGL0LkgR1BVLdGC0YDQtdC90LXRgDoge2JhY2tlbmR9Ljxicj7QoNC10LLQuNC30LjRjyDQuNGB0YLQvtGH0L3QuNC60LA6IHtyZXZpc2lvbn0uPGJyPgpTQUZFNzA6IEhvdCBTcG90IDcwwrBDIMOXIDMsIDc1wrBDINC90LXQvNC10LTQu9C10L3QvdC+OyDQv9C+0YLQtdGA0Y8g0LTQsNGC0YfQuNC60LAgPSBIT0xELjxicj4K0KHRgtGA0LDQvdC40YbQsCDQvtCx0L3QvtCy0LvRj9C10YLRgdGPINC60LDQttC00YvQtSAzMCDRgdC10LrRg9C90LQuINCU0LvRjyDQvtCx0L3QvtCy0LvQtdC90LjRjyDQtNCw0L3QvdGL0YUg0LfQsNC/0YPRgdGC0LjRgtC1INC/0YDQvtCy0LXRgNC60YMg0YHQtdCz0LzQtdC90YLQvtCyINC/0L7QstGC0L7RgNC90L47INCx0LXQtyDQvdC+0LLRi9GFINC/0YDQvtCy0LXRgNC10L3QvdGL0YUg0YfQtdC60L/QvtC40L3RgtC+0LIg0LfQvdCw0YfQtdC90LjQtSAwLzgg0L3QtSDQvNC10L3Rj9C10YLRgdGPLgo8L2Zvb3Rlcj48L21haW4+PC9ib2R5PjwvaHRtbD4='
    ).decode('utf-8')
    substitutions = {
        'status': escape(plan['status']),
        'done': str(plan['completed_training_segments']),
        'cells': ''.join(cells),
        'inherited': 'Проверен' if plan['verified_inheritance'] else 'Ожидается',
        'backend': escape(plan['segment_training_backend']),
        'revision': escape(str(plan.get('source_revision', 'PENDING'))),
    }
    html = template
    for key, value in substitutions.items():
        html = html.replace('{' + key + '}', value)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as fp:
        fp.write(html)
        temp_name = fp.name
    os.replace(temp_name, path)

def sha256_file(path, chunk=8*1024*1024):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def inspect(root, full_hash=False):
    model = root / 'models' / 'NOX_PRIME_9B_INHERITED'
    manifest = root / 'NOX_PRIME_9B_MANIFEST.json'
    state_path = root / 'NOX_9B_SEGMENT_PLAN.json'
    results = {
        'schema': 'nox.segment-plan.v1',
        'updated_utc': now(),
        'model_dir': str(model),
        'inheritance_manifest': str(manifest),
        'status': 'WAIT_FOR_COMPLETE_INHERITANCE',
        'base_weights_read_only': True,
        'training_started': False,
        'segment_training_backend': 'NOT_VERIFIED_ON_RX6650M_DIRECTML',
        'completed_training_segments': 0,
        'verified_inheritance': False,
        'stages': [
            {'segment_id': f'S{i+1:02d}', 'layers': list(range(i*4, i*4+4)),
             'status': 'NOT_TRAINED', 'tensor_count': 0, 'shards': []}
            for i in range(STAGE_COUNT)
        ],
        'shared_components': ['embed_tokens','lm_head','final_norm','vision_tower','other_non_layer_tensors'],
        'safety': {'hot_spot_url': 'http://127.0.0.1:8085/data.json',
                   'device': 'AMD Radeon RX 6650M',
                   'stop_after_three_at_or_above_c': 70,
                   'immediate_stop_c': 75,
                   'sensor_lost': 'HOLD',
                   'minimum_cooldown_s': 180},
    }
    if not manifest.is_file() or not model.is_dir():
        atomic_json(state_path, results)
        return results
    previous = json.loads(manifest.read_text(encoding='utf-8-sig'))
    if previous.get('status') != 'INHERITED_UNTRAINED':
        raise RuntimeError('Unexpected original manifest status; original files untouched')
    if Path(previous.get('model_root','')) != model:
        raise RuntimeError('Original manifest model_root mismatch; no change')
    weights = previous.get('shards') or []
    if not weights:
        raise RuntimeError('Original manifest has no verified weight shards')
    for s in weights:
        name=s.get('file','')
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('Unsafe shard path in manifest')
        p = model / name
        if not p.is_file() or p.stat().st_size != s.get('bytes'):
            raise RuntimeError('NO-LOSS HOLD: missing/changed weight shard: '+name)
        if not s.get('sha256'):
            raise RuntimeError('NO-LOSS HOLD: original manifest missing SHA for '+name)
        if full_hash and sha256_file(p).lower() != s['sha256'].lower():
            raise RuntimeError('NO-LOSS HOLD: SHA mismatch: '+name)
    index = model / 'model.safetensors.index.json'
    if not index.is_file():
        # Safetensors keys cannot be inferred from filename; don't fabricate layer mapping.
        results['status'] = 'HOLD_NO_TENSOR_INDEX'
        results['reason'] = 'Source shards exist, but model.safetensors.index.json is missing. Exact layer mapping not inferred.'
        atomic_json(state_path, results)
        return results
    weight_map = json.loads(index.read_text(encoding='utf-8-sig')).get('weight_map')
    if not isinstance(weight_map, dict) or len(weight_map) < 100:
        raise RuntimeError('NO-LOSS HOLD: suspicious weight map')
    shard_names = {w['file'] for w in weights}
    unexpected = set(weight_map.values()) - shard_names
    if unexpected:
        raise RuntimeError('NO-LOSS HOLD: tensor points to missing shard(s): '+repr(sorted(unexpected)))
    found=set()
    shared=set()
    for key, shard in weight_map.items():
        m=LAYER.search(key)
        if not m:
            shared.add(key)
            continue
        layer=int(m.group(1))
        if not 0 <= layer < EXPECTED_LAYERS:
            raise RuntimeError('Layer index out of expected 0-31 range: '+key)
        found.add(layer)
        stage=results['stages'][layer//4]
        stage['tensor_count']+=1
        if shard not in stage['shards']:
            stage['shards'].append(shard)
    if found != set(range(EXPECTED_LAYERS)):
        raise RuntimeError(f'NO-LOSS HOLD: expected 32 layers, found {sorted(found)}')
    results['verified_inheritance'] = True
    results['source_repository']=previous.get('source_repository')
    results['source_revision']=previous.get('source_revision')
    results['base_weight_bytes']=previous.get('weights_bytes')
    results['index_tensors']=len(weight_map)
    results['shared_tensors']=len(shared)
    results['status']='ALL_32_LAYERS_MAPPED_TRAINING_PENDING'
    results['verification_level']='manifest_bytes+tensor_index'+('+fresh_sha256' if full_hash else '')
    for stage in results['stages']:
        stage['shards'].sort()
        if not stage['tensor_count']:
            raise RuntimeError('Empty model stage: '+stage['segment_id'])
    atomic_json(state_path, results)
    return results


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--root',type=Path,default=ROOT_DEFAULT)
    a.add_argument('--full-sha',action='store_true',help='Recheck weight bytes against inherited SHA-256 (slow)')
    args=a.parse_args()
    try:
        x=inspect(args.root,args.full_sha)
        print('NOX 9B PLAN:',x['status'])
        print('9B source:',x.get('source_revision','PENDING'))
        print('Base weights preserved:',x['base_weights_read_only'])
        print('Segments with actual 9B training receipts:',x['completed_training_segments'],'/8')
        print('GPU training backend:',x['segment_training_backend'])
        print('File:',args.root/'NOX_9B_SEGMENT_PLAN.json')
        if x['status']=='ALL_32_LAYERS_MAPPED_TRAINING_PENDING':
            print('No GPU training claimed: training engine still requires physical DirectML verification.')
        return 0 if x['verified_inheritance'] else 2
    except Exception as e:
        print('NOX 9B SEGMENT HOLD:',str(e),file=sys.stderr)
        return 3

if __name__=='__main__':
    sys.exit(main())