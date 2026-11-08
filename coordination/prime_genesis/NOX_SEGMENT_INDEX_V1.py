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
    template = '''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>NOX PRIME · сегментный контроль</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 60% -30%,#3e3119,#111211 60%,#080909);color:#eee8df;font:15px system-ui,Arial}
main{max-width:1040px;margin:auto;padding:35px 22px 70px}.eyebrow{color:#d7b073;font-size:12px;letter-spacing:.24em}
h1{font-weight:500;letter-spacing:.1em;font-size:28px}.statusbar{border:1px solid #504332;border-radius:12px;padding:13px;color:#dfc290;overflow-wrap:anywhere}.total{font-size:52px;color:#e8be75;margin-top:24px}.hint{color:#b5ab9e;font-size:12px}
.grid{margin-top:23px;display:grid;grid-template-columns:repeat(4,1fr);gap:12px}article{min-height:147px;padding:18px;background:linear-gradient(140deg,#29241b,#111515);border:1px solid #48402e;border-radius:14px}
.num{font-size:22px;color:#e3ba70}.layers{margin-top:6px;color:#c5b8a2;font-size:13px}.status{color:#e2a763;font-size:12px;margin-top:21px}.count{font-size:11px;color:#969390;margin-top:6px}
footer{border-top:1px solid #54442e;margin-top:36px;padding-top:22px;color:#aaa298;font-size:13px;line-height:1.8;overflow-wrap:anywhere}@media(max-width:720px){.grid{grid-template-columns:repeat(2,1fr)}}
</style></head><body><main><div class="eyebrow">NOX HELION · FORGE</div>
<h1>СЕГМЕНТЫ 9B / NO-LOSS</h1><div class="statusbar">Состояние: {status}</div>
<div class="total">{done} / 8</div><div class="hint">Физически проверенных обученных сегментов. Не «процент интеллекта».</div>
<div class="grid">{cells}</div><footer>Полный набор 9B-весов: {inherited}. Исходные веса сохраняются без изменения.<br>
Реальный GPU-тренер: {backend}.<br>Ревизия источника: {revision}.<br>
SAFE70: Hot Spot 70°C × 3, 75°C немедленно; потеря датчика = HOLD.<br>
Страница обновляется каждые 30 секунд. Для обновления данных запустите проверку сегментов повторно; без новых проверенных чекпоинтов значение 0/8 не меняется.
</footer></main></body></html>'''
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