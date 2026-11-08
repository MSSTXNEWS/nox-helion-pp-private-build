"""NOX HELION FORGE V6 — local read-only live control.

Uses the existing V5 backend for real SAFE70/DirectML, Ollama, LHM and LoRA
checkpoint state. Adds optional psutil/system and LHM workload metrics.
All unavailable metrics are null, never synthetic. Binds localhost ONLY.
No writes to training/database/models and no Web STOP endpoint.
"""
from __future__ import annotations
import argparse
import hashlib
import ctypes
import json
import re
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit, parse_qs

try:
    import psutil
except ImportError:
    psutil = None

HERE = Path(__file__).resolve().parent
ROOT = Path(r'C:\NOX_HELION\NOX_NEW')

try:
    import forge_genesis_server_v8 as old
except ImportError as exc:
    raise SystemExit('Place original forge_genesis_server_v8.py + its helpers next to V6') from exc

SCHEMA = 'NOX-FORGE-FOCUS-LIVE-v1'
TARGET_STEPS = 11120  # User-selected cumulative target: 1120 + 10000 new steps.
_latest_process_samples: dict[int, tuple[float, float]] = {}
_lock = threading.Lock()


def safe_number(v):
    try:
        number = float(v)
        return round(number, 2) if number == number and abs(number) < 1e14 else None
    except (TypeError, ValueError):
        return None


def lhm_workload():
    """Only read discrete Radeon RX 6650M subtree in LHM /data.json."""
    out = dict(gpu_load_pct=None, gpu_memory_used_gib=None,
               gpu_memory_total_gib=None, cpu_temp_c=None)
    try:
        with urlopen('http://127.0.0.1:8085/data.json', timeout=3) as res:
            tree = json.loads(res.read(2_000_000))
    except (OSError, ValueError, UnicodeError):
        return out

    def measure(node, context=None, depth=0):
        if not isinstance(node, dict) or depth > 36:
            return
        name = str(node.get('Text', '')).strip()
        val = str(node.get('Value', ''))
        if re.search(r'RX\s*6650M', name, re.I):
            context = 'gpu'
        elif re.search(r'(?:Radeon|GeForce|NVIDIA)', name, re.I) and ('6650M' not in name):
            context = 'othergpu'
        elif re.search(r'Ryzen|Intel Core|AMD CPU', name, re.I):
            context = 'cpu'
        found = re.search(r'([0-9]+(?:[.,][0-9]+)?)\s*(%|°\s*C|GiB|GB|MiB|MB)', val, re.I)
        if found:
            x = float(found.group(1).replace(',', '.'))
            unit = found.group(2).replace(' ', '').lower()
            if context == 'gpu':
                if 'gpu core' in name.lower() and unit == '%' and 0 <= x <= 100:
                    out['gpu_load_pct'] = x
                elif 'gpu memory used' in name.lower() and unit in ('gib', 'gb', 'mib', 'mb'):
                    out['gpu_memory_used_gib'] = round(x / (1024 if unit in ('mib', 'mb') else 1), 2)
                elif 'gpu memory total' in name.lower() and unit in ('gib', 'gb', 'mib', 'mb'):
                    out['gpu_memory_total_gib'] = round(x / (1024 if unit in ('mib', 'mb') else 1), 2)
            elif context == 'cpu' and name.lower() in ('cpu package', 'cpu tctl/tdie') and unit == '°c':
                out['cpu_temp_c'] = x
        for child in node.get('Children') or []:
            measure(child, context, depth + 1)
    measure(tree)
    return out


def system_snapshot():
    out = dict(cpu_usage_pct=None, ram_usage_pct=None, ram_used_gib=None,
               ram_total_gib=None, total_process_count=None, processes=[],
               disk_used_gib=None, disk_total_gib=None, data_source='none')
    try:
        disk = shutil.disk_usage(ROOT)
        out['disk_used_gib'] = round(disk.used / 2**30, 2)
        out['disk_total_gib'] = round(disk.total / 2**30, 2)
    except OSError:
        pass
    if psutil is None:
        # Windows standard-library fallback for real physical memory and CPU-load.
        if sys.platform == 'win32':
            class Memory(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                            ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            m = Memory()
            m.dwLength = ctypes.sizeof(m)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                out['ram_usage_pct'] = int(m.dwMemoryLoad)
                out['ram_total_gib'] = round(m.ullTotalPhys / 2**30, 2)
                out['ram_used_gib'] = round((m.ullTotalPhys - m.ullAvailPhys) / 2**30, 2)
            out['data_source'] = 'Win32 GlobalMemoryStatusEx'
        return out
    out['cpu_usage_pct'] = psutil.cpu_percent(interval=.12)
    memory = psutil.virtual_memory()
    out['ram_usage_pct'] = round(memory.percent, 1)
    out['ram_used_gib'] = round(memory.used / 2**30, 2)
    out['ram_total_gib'] = round(memory.total / 2**30, 2)
    try:
        out['total_process_count'] = len(psutil.pids())
    except (OSError, psutil.Error):
        pass
    names = ('python', 'ollama', 'nox', 'webview', 'librehardwaremonitor')
    now = time.monotonic()
    selected = []
    with _lock:
        for p in psutil.process_iter(['pid', 'name', 'cpu_times', 'memory_info']):
            try:
                name = p.info.get('name') or ''
                if not any(token in name.lower() for token in names):
                    continue
                pid = p.pid
                c = p.info.get('cpu_times')
                cpu = (c.user + c.system) if c is not None else 0.0
                prev = _latest_process_samples.get(pid)
                utilization = round(max(0.0, 100.0 * (cpu - prev[0]) / (now - prev[1])), 1) if prev and now > prev[1] else None
                _latest_process_samples[pid] = (cpu, now)
                mem = p.info.get('memory_info')
                selected.append({'name': name, 'pid': pid, 'cpu_pct': utilization,
                                 'ram_mib': round(mem.rss / 2**20, 1) if mem is not None else None})
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                continue
        alive = {x['pid'] for x in selected}
        for pid in list(_latest_process_samples):
            if pid not in alive:
                del _latest_process_samples[pid]
    selected.sort(key=lambda x: ((x['cpu_pct'] if x['cpu_pct'] is not None else -1),
                                 (x['ram_mib'] if x['ram_mib'] is not None else 0)), reverse=True)
    out['processes'] = selected[:12]
    out['data_source'] = 'psutil'
    return out


def checkpoint_count(root):
    p = root / 'brain' / 'intelligence' / 'adapters'
    if not p.is_dir():
        return 0
    count = 0
    for run in p.iterdir():
        if not run.is_dir() or run.is_symlink() or not run.name.startswith(('SAFE65_', 'NOX_GPU_', 'GPU_', 'NOX_RESUME_')):
            continue
        for cp in run.glob('step-*'):
            if cp.is_dir() and not cp.is_symlink() and (cp / 'adapter_model.safetensors').is_file() and (cp / 'adapter_config.json').is_file():
                count += 1
    return count


def evaluation(root):
    """Only an explicit externally evaluated score, never a progress guess."""
    path = root / 'brain' / 'telemetry' / 'core_evaluation.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if payload.get('verified') is not True or not payload.get('benchmark'):
            return None
        score = safe_number(payload.get('score_percent'))
        if score is None or not 0 <= score <= 100:
            return None
        return {'score_percent': score, 'benchmark': str(payload['benchmark'])[:120],
                'measured_at': payload.get('measured_at')}
    except (OSError, ValueError, TypeError):
        return None


def live_status(root):
    d = old.forge_focus_live(root)
    d['system'] = system_snapshot()
    d['load'] = lhm_workload()
    d['goal_steps'] = TARGET_STEPS
    d['goal_source'] = 'User requested +10000 after 1120 saved steps'
    d['overall_progress_pct'] = round(100 * max(0, min(d['saved_step'], TARGET_STEPS)) / TARGET_STEPS, 2) if isinstance(d.get('saved_step'), int) else None
    d['saved_checkpoints'] = checkpoint_count(root)
    d['intelligence_evaluation'] = evaluation(root)
    try:
        from nox_prime_progress_v1 import read_progress
        d['prime_pipeline']=read_progress(root)
    except (OSError,ValueError,TypeError,ImportError):
        d['prime_pipeline']=None
    d['read_only'] = True
    d['thermal_cutoff_c'] = 70
    d['thermal_resume_below_c'] = 65
    d['thermal_cooldown_s'] = 180
    d['timestamp_utc'] = datetime.now(timezone.utc).isoformat()
    return d


def serve(root, port):
    # Running-code fingerprint: local boot must not attach to stale V6 instances.
    running_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    import nox_unified_brain_v1 as unified
    from nox_prime_forge_job_v1 import ForgeManager
    forge_manager=ForgeManager(root,root/"brain"/"source"/"repo")
    from nox_prime_autonomous_router_v1 import decide as decide_work, format_ack
    page = (HERE / 'forge_wow_live_v6.html').read_bytes()
    unified_page = (HERE / 'nox_unified_chat_v1.html').read_bytes()
    visual = HERE / 'forge_focus_v4_canonical_live.html'
    class Handler(BaseHTTPRequestHandler):
        def get(self, payload, content_type, code=200):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(payload)
        def do_GET(self):
            if self.path in ('/', '/index.html'):
                return self.get(page, 'text/html; charset=utf-8')
            if self.path == '/nox/chat':
                return self.get(unified_page, 'text/html; charset=utf-8')
            if self.path == '/api/nox/resource-advice':
                try:
                    import nox_prime_resource_advisor_v1 as resource
                    observed=resource.snapshot()
                    recommendation=resource.advise('general',observed)
                    return self.get(json.dumps(recommendation,ensure_ascii=False).encode('utf-8'),
                                    'application/json; charset=utf-8')
                except Exception as exc:
                    return self.get(json.dumps({'error':type(exc).__name__}).encode(),
                                    'application/json',503)
            if self.path == '/api/nox/forge/status':
                try:
                    return self.get(json.dumps(forge_manager.status(),ensure_ascii=False).encode('utf-8'),
                                    'application/json; charset=utf-8')
                except Exception as exc:
                    return self.get(json.dumps({'error':type(exc).__name__}).encode(),
                                    'application/json',503)
            if self.path == '/api/nox/pipeline':
                try:
                    from nox_prime_progress_v1 import read_progress
                    data=read_progress(root)
                    return self.get(json.dumps(data,ensure_ascii=False).encode('utf-8'),
                                    'application/json; charset=utf-8')
                except Exception as exc:
                    return self.get(json.dumps({'error':type(exc).__name__}).encode(),
                                    'application/json',503)
            if self.path == '/api/nox/cores':
                try:
                    from nox_prime_core_matrix_v1 import matrix
                    from nox_prime_experience_v1 import project
                    status=unified.status(root)
                    count=project(root,max_examples=1)['count']
                    result=matrix(root,status.get('installed_models',[]),
                                  count,status.get('soul_affect',{}).get('available') is True)
                    return self.get(json.dumps(result,ensure_ascii=False).encode('utf-8'),
                                    'application/json; charset=utf-8')
                except Exception as ex:
                    return self.get(json.dumps({'error':type(ex).__name__}).encode(),
                                    'application/json',503)
            if urlsplit(self.path).path == '/api/nox/experience':
                try:
                    from nox_prime_experience_v1 import project
                    parts=parse_qs(urlsplit(self.path).query)
                    query=(parts.get('q') or [''])[0][:300]
                    result=project(root,query=query,max_examples=5)
                    return self.get(json.dumps(result,ensure_ascii=False).encode('utf-8'),
                                    'application/json; charset=utf-8')
                except Exception as exc:
                    return self.get(json.dumps({'error':type(exc).__name__}).encode(),
                                    'application/json',503)
            if self.path == '/api/nox/soul/status':
                try:
                    from nox_prime_affect_runtime_v1 import status as soul_status
                    payload=soul_status(root)
                    return self.get(json.dumps(payload,ensure_ascii=False).encode('utf-8'),
                                    'application/json; charset=utf-8')
                except Exception as exc:
                    return self.get(json.dumps({'error':type(exc).__name__}).encode(),
                                    'application/json',503)
            if self.path == '/api/nox/cognition/status':
                # Stats only, no transcript excerpts or unauthorized Persona data.
                try:
                    import nox_prime_memory_continuum_v1 as cognitive
                    d=cognitive.snapshot(root)
                    return self.get(json.dumps({
                        'schema':'NOX-COGNITIVE-CANDIDATE-V1',
                        'layers':d['layers'],
                        'm0_events_total':d['m0_events_total'],
                        'fast_events':len(d['fast_session']),
                        'medium_events':len(d['medium_episodes']),
                        's03_written':False,
                        'skills_promoted':False
                    },ensure_ascii=False).encode('utf-8'),
                    'application/json; charset=utf-8')
                except Exception as ex:
                    return self.get(json.dumps({'error':type(ex).__name__}).encode(),
                                    'application/json',503)
            if self.path == '/api/nox/history':
                try:
                    return self.get(json.dumps({'messages':unified.read_history(root)},
                                               ensure_ascii=False).encode('utf-8'),
                                    'application/json; charset=utf-8')
                except Exception as ex:
                    return self.get(json.dumps({'error':type(ex).__name__}).encode(),
                                    'application/json',503)
            if self.path == '/api/nox/status':
                try:
                    result=unified.status(root)
                    return self.get(json.dumps(result,ensure_ascii=False).encode('utf-8'),
                                    'application/json; charset=utf-8')
                except Exception as ex:
                    return self.get(json.dumps({'error':type(ex).__name__}).encode(),
                                    'application/json',503)
            if self.path == '/visual' and visual.is_file():
                return self.get(visual.read_bytes(), 'text/html; charset=utf-8')
            if self.path == '/api/health':
                return self.get(json.dumps({'status': 'READY', 'schema': SCHEMA,
                                            'template': 'NOX-FORGE-WOW-LIVE-V6',
                                            'unified_router':'NOX-UNIFIED-BRAIN-V6',
                                            'read_only_native_s03': True,
                                            'local_chat_journal': True,
                                            'soul_runtime':'EN_HOLDOUT_ONLY',
                                            'semantic_retrieval':'ON_DEMAND_LOCAL',
                                            'source_sha256':running_source_sha256}).encode(), 'application/json')
            if self.path == '/api/status':
                try:
                    payload = live_status(root)
                    return self.get(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8')
                except Exception as exc:
                    return self.get(json.dumps({'error': type(exc).__name__, 'detail': str(exc)[:220]}).encode(), 'application/json', 503)
            return self.get(b'{"error":"not found"}', 'application/json', 404)
        def do_POST(self):
            if self.path not in ('/api/nox/chat','/api/nox/chat/stream','/api/nox/forge/start'):
                return self.get(b'{"error":"read-only; no GPU command bridge"}',
                                'application/json',403)
            # Never accept arbitrary cross-site requests into local Ollama.
            host=self.headers.get("Host","")
            origin=self.headers.get("Origin","")
            permitted=("127.0.0.1:"+str(port),"localhost:"+str(port))
            if host not in permitted or (origin and origin not in (
                "http://127.0.0.1:"+str(port),"http://localhost:"+str(port))):
                return self.get(b'{"error":"ORIGIN_DENIED"}','application/json',403)
            if self.headers.get("Content-Type","").split(";")[0].strip().lower()!="application/json":
                return self.get(b'{"error":"JSON_REQUIRED"}','application/json',415)
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=240000:raise ValueError("REQUEST_SIZE")
                payload=json.loads(self.rfile.read(length))
                # The latest direct USER message can automatically request a
                # bounded FORGE stage, without any second button or model hint.
                # RAG, recalled memory and tool outputs never authorize work.
                job=None
                if (self.path in ('/api/nox/chat','/api/nox/chat/stream')
                    and isinstance(payload,dict)):
                    intent=decide_work(payload.get('message'))
                    if intent:
                        job=forge_manager.start(intent['target'],intent['objective'])
                        ack=format_ack(job)
                        unified.save_turn(root,payload['message'].strip(),ack)
                if self.path == '/api/nox/forge/start':
                    if not isinstance(payload,dict):
                        raise ValueError('BODY_MUST_BE_OBJECT')
                    obj=forge_manager.start(payload.get('target','chat'),
                                            payload.get('objective'))
                    return self.get(json.dumps(obj,ensure_ascii=False).encode('utf-8'),
                                    'application/json; charset=utf-8')
                if job is not None and self.path == '/api/nox/chat/stream':
                    events=({'type':'start','model':'NOX_FORGE_ACTION'},
                            {'type':'delta','text':ack},
                            {'type':'done','model':'NOX_FORGE_ACTION',
                             'saved':True,'job_id':job['job_id']})
                    self.send_response(200)
                    self.send_header('Content-Type','application/x-ndjson; charset=utf-8')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.end_headers()
                    for event in events:
                        self.wfile.write((json.dumps(event,ensure_ascii=False)+'\n').encode('utf-8'))
                        self.wfile.flush()
                    return
                if job is not None and self.path == '/api/nox/chat':
                    return self.get(json.dumps({'identity':'NOX PRIME',
                        'answer':ack,'model':'NOX_FORGE_ACTION','job_id':job['job_id'],
                        'history_persisted':True,'stage':'FORGE_CANDIDATE_ONLY',
                        's03_integrated':False},ensure_ascii=False).encode('utf-8'),
                        'application/json; charset=utf-8')
                if self.path == '/api/nox/chat/stream':
                    # Validate payload and upstream connection before streaming headers.
                    gen=unified.stream_chat(root,payload)
                    first=next(gen)
                    self.send_response(200)
                    self.send_header('Content-Type','application/x-ndjson; charset=utf-8')
                    self.send_header('Cache-Control','no-store, no-transform')
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.end_headers()
                    try:
                        for evt in (first, *()):
                            self.wfile.write((json.dumps(evt,ensure_ascii=False)+'\n').encode('utf-8'))
                            self.wfile.flush()
                        for evt in gen:
                            self.wfile.write((json.dumps(evt,ensure_ascii=False)+'\n').encode('utf-8'))
                            self.wfile.flush()
                    except (BrokenPipeError,ConnectionResetError):
                        pass
                    except Exception as ex:
                        try:
                            self.wfile.write((json.dumps({'type':'error','error':str(ex)[:200]},
                                                         ensure_ascii=False)+'\n').encode('utf-8'))
                            self.wfile.flush()
                        except OSError:
                            pass
                    finally:
                        gen.close()
                    return
                result=unified.chat(root,payload)
                return self.get(json.dumps(result,ensure_ascii=False).encode('utf-8'),
                                'application/json; charset=utf-8')
            except (ValueError,TypeError) as ex:
                return self.get(json.dumps({'error':str(ex)[:160]}).encode('utf-8'),
                                'application/json',400)
            except Exception as ex:
                return self.get(json.dumps({'error':type(ex).__name__+': '+str(ex)[:160]}).encode('utf-8'),
                                'application/json',503)
        def log_message(self, *_):
            pass
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--port', type=int, default=18877)
    args = p.parse_args()
    serve(args.root.resolve(), args.port)