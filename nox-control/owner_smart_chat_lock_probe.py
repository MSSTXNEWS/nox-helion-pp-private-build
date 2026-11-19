#!/usr/bin/env python3
"""Bounded metadata-only maintenance lock and current chat predecessor probe."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time

ROOT = Path('/root/nox')
LOCK = ROOT / 'state/owner_maintenance.lock'
SITE = ROOT / 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
PATHS = {name: ROOT / 'scripts' / name for name in (
    'owner_chat_stream.py', 'nox_v29_chat_bridge.py', 'chat_proxy.py',
    'agent_loop.py', 'nox_tools.py', 'owner_chat_evidence.py')}
PATHS['nox-v24-chat.js'] = SITE / 'pc/v24/nox-v24-chat.js'
SERVICES = ('nox-proxy', 'nox-ds41-8098', 'nox-web29-18775', 'nox-dispatcher-t855u')


def bounded(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > limit:
            raise ValueError('READ_SCOPE')
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > limit:
            raise ValueError('READ_LIMIT')
        return bytes(raw)
    finally:
        os.close(fd)


def process(pid):
    raw = bounded('/proc/%d/stat' % pid, 8192).decode('ascii', 'replace')
    parts = raw[raw.rfind(')') + 2:].split()
    comm = bounded('/proc/%d/comm' % pid, 256).decode('ascii', 'replace').strip()
    out = {'pid': pid, 'ppid': int(parts[1]), 'pgrp': int(parts[2]),
           'start_ticks': int(parts[19]), 'state': parts[0],
           'comm': comm if re.fullmatch(r'[A-Za-z0-9_.:+-]{1,80}', comm) else 'OTHER'}
    args = bounded('/proc/%d/cmdline' % pid, 32768).split(b'\0')
    out['nox_script_basenames'] = sorted(set(
        os.path.basename(os.fsdecode(a)) for a in args
        if a.startswith(b'/root/nox/') and re.fullmatch(rb'/[A-Za-z0-9_./-]{1,300}\.py', a)))[:5]
    return out


def file_state(path):
    try:
        raw = bounded(path, 1048576)
        return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    except FileNotFoundError:
        return {'state': 'ABSENT'}
    except Exception as exc:
        return {'state': 'UNAVAILABLE', 'error_type': type(exc).__name__}


def lock_state():
    try:
        info = os.stat(LOCK, follow_symlinks=False)
    except FileNotFoundError:
        return {'state': 'ABSENT', 'holders': []}
    if not stat.S_ISREG(info.st_mode):
        return {'state': 'NONREGULAR', 'holders': []}
    device = (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino)
    out = {'state': 'OBSERVED', 'device_major': device[0], 'device_minor': device[1],
           'inode': device[2], 'mode': oct(stat.S_IMODE(info.st_mode)), 'holders': []}
    lines = bounded('/proc/locks', 2097152).decode('ascii', 'replace').splitlines()
    for line in lines:
        parts = line.split()
        waiting = '->' in parts
        if waiting:
            parts.remove('->')
        if len(parts) < 8:
            continue
        try:
            major, minor, inode = parts[5].split(':')
            key = (int(major, 16), int(minor, 16), int(inode))
            pid = int(parts[4])
        except (ValueError, IndexError):
            continue
        if key != device:
            continue
        row = {'waiting': waiting, 'kind': parts[1] if parts[1] in ('FLOCK', 'POSIX', 'OFDLCK') else 'OTHER',
               'mode': parts[3] if parts[3] in ('READ', 'WRITE') else 'OTHER', 'pid': pid}
        if pid > 0:
            try:
                row['process'] = process(pid)
                if row['process']['ppid'] > 0:
                    row['parent'] = process(row['process']['ppid'])
                matches = []
                for item in list(Path('/proc/%d/fd' % pid).iterdir())[:512]:
                    try:
                        candidate = item.stat()
                        if (candidate.st_dev, candidate.st_ino) == (info.st_dev, info.st_ino):
                            matches.append(int(item.name))
                    except (OSError, ValueError):
                        pass
                row['matching_fds'] = sorted(matches)
            except Exception as exc:
                row['process_error_type'] = type(exc).__name__
        out['holders'].append(row)
        if len(out['holders']) >= 20:
            break
    out['currently_locked'] = any(not row['waiting'] for row in out['holders'])
    return out


def services():
    result = {}
    for name in SERVICES:
        try:
            run = subprocess.run(['supervisorctl', 'status', name], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4,
                env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            raw = run.stdout[:8192]
            tokens = raw.split()
            row = {'state': tokens[1].decode('ascii', 'replace') if len(tokens) > 1 else 'UNKNOWN'}
            match = re.search(rb'\bpid ([0-9]{1,10}),', raw)
            if match:
                row['process'] = process(int(match[1]))
            result[name] = row
        except Exception as exc:
            result[name] = {'state': 'UNAVAILABLE', 'error_type': type(exc).__name__}
    return result


def credential_reader_shape():
    """AST structure only: no source fragments or credential literal values."""
    try:
        tree = ast.parse(bounded(PATHS['chat_proxy.py'], 1048576))
        readers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_read_chat_password']
        if len(readers) != 1:
            return {'state': 'UNAVAILABLE'}
        node = readers[0]
        safe_names = sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name) and
                             re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,79}', n.id)})
        safe_attrs = sorted({n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute) and
                             re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,79}', n.attr)})
        return {'state': 'AST_PRESENT', 'node_types': sorted({type(n).__name__ for n in ast.walk(node)}),
                'names': safe_names, 'attributes': safe_attrs, 'arguments': len(node.args.args),
                'runtime_module_imported': False}
    except Exception as exc:
        return {'state': 'UNAVAILABLE', 'error_type': type(exc).__name__}


def cognitive_and_budget_metadata():
    namespace={'__name__':'_reviewed_metadata_only'}
    exec(compile('"""Bounded read-only metadata/token-count appendix; never generates model output.\n\nNo native imports, source bodies, prompts, token IDs, credentials or environment\ncontents are exported. Model HTTP is restricted to loopback:8098 and three\nnon-inference endpoints. The synthetic prompt is fixed below.\n"""\nfrom __future__ import annotations\nimport ast\nimport hashlib\nimport json\nimport os\nfrom pathlib import Path\nimport re\nimport stat\nimport time\nimport urllib.error\nimport urllib.request\n\nROOT=Path(\'/root/nox/scripts\')\nPROTOCOL=frozenset((\'messages\',\'content\',\'tools\',\'max_tokens\',\'n_predict\',\'output_tokens\',\n    \'budget\',\'n_ctx\',\'n_ctx_per_seq\',\'context\',\'context_size\',\'selected_url\',\'cache_prompt\',\n    \'chat_template_kwargs\',\'enable_thinking\',\'thinking_mode\',\'chat\',\'stream\',\'role\',\'user\'))\n\n\ndef _read(path,limit=250000):\n    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)\n    with os.fdopen(fd,\'rb\') as f:\n        info=os.fstat(f.fileno())\n        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:\n            raise ValueError(\'BOUNDED_SOURCE_REQUIRED\')\n        raw=f.read(limit+1)\n        if len(raw)>limit:raise ValueError(\'SOURCE_LIMIT\')\n        return raw\n\n\ndef _name(node):\n    if isinstance(node,ast.Name):return node.id\n    if isinstance(node,ast.Attribute):return _name(node.value)+\'.\'+node.attr\n    return \'\'\n\n\ndef _safe_expr(node):\n    if isinstance(node,ast.Constant):\n        return node.value if isinstance(node.value,(int,float,bool,type(None))) or node.value in PROTOCOL else \'<string>\'\n    if isinstance(node,ast.Name):return {\'name\':node.id}\n    if isinstance(node,ast.Attribute):return {\'attribute\':_name(node)}\n    if isinstance(node,ast.Call):\n        return {\'call\':_name(node.func),\'args\':[_safe_expr(x) for x in node.args[:4]],\n                \'kwargs\':{x.arg:_safe_expr(x.value) for x in node.keywords[:4] if x.arg}}\n    if isinstance(node,ast.BinOp):\n        return {\'op\':type(node.op).__name__,\'left\':_safe_expr(node.left),\'right\':_safe_expr(node.right)}\n    if isinstance(node,ast.UnaryOp):return {\'op\':type(node.op).__name__,\'operand\':_safe_expr(node.operand)}\n    if isinstance(node,ast.Subscript):return {\'base\':_safe_expr(node.value),\'key\':_safe_expr(node.slice)}\n    if isinstance(node,ast.Compare):return {\'left\':_safe_expr(node.left),\'ops\':[type(x).__name__ for x in node.ops],\n                                           \'right\':[_safe_expr(x) for x in node.comparators[:4]]}\n    if isinstance(node,ast.BoolOp):return {\'op\':type(node.op).__name__,\'values\':[_safe_expr(x) for x in node.values[:6]]}\n    return {\'shape\':type(node).__name__}\n\n\ndef _metadata(path,wanted):\n    raw=_read(path);source=raw.decode(\'utf-8\');tree=ast.parse(source)\n    result={\'name\':path.name,\'sha256\':hashlib.sha256(raw).hexdigest(),\'bytes\':len(raw),\'functions\':[]}\n    constants={}\n    for n in tree.body:\n        if isinstance(n,(ast.Assign,ast.AnnAssign)):\n            targets=n.targets if isinstance(n,ast.Assign) else [n.target]\n            for target in targets:\n                if (isinstance(target,ast.Name) and re.search(\'BUDGET|TOKEN|CONTEXT|CTX|RESERVE|MARGIN|TTL\',target.id)\n                        and not re.search(\'AUTH|SECRET|PASSWORD|KEY|COOKIE|SESSION\',target.id)):\n                    if isinstance(n.value,ast.Constant) and isinstance(n.value.value,(int,float,bool)):\n                        constants[target.id]=n.value.value\n    result[\'numeric_constants\']=constants\n    for fn in ast.walk(tree):\n        if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)) or fn.name not in wanted:continue\n        args=fn.args.posonlyargs+fn.args.args\n        defaults={a.arg:_safe_expr(v) for a,v in zip(args[-len(fn.args.defaults):],fn.args.defaults)} if fn.args.defaults else {}\n        defaults.update({a.arg:_safe_expr(v) for a,v in zip(fn.args.kwonlyargs,fn.args.kw_defaults) if v is not None})\n        strings={n.value for n in ast.walk(fn) if isinstance(n,ast.Constant) and isinstance(n.value,str)}\n        selected_calls=[]\n        for call in ast.walk(fn):\n            if not isinstance(call,ast.Call):continue\n            name=_name(call.func)\n            key=call.args[0].value if call.args and isinstance(call.args[0],ast.Constant) else None\n            if (name.endswith((\'trim_messages\',\'_trim_ctx\',\'prepare_payload\')) or\n                    name.endswith((\'.get\',\'.setdefault\')) and key in PROTOCOL):\n                selected_calls.append(_safe_expr(call))\n        result[\'functions\'].append({\'name\':fn.name,\'parameters\':[a.arg for a in args+fn.args.kwonlyargs],\n            \'defaults\':defaults,\'selected_calls\':selected_calls[:32],\n            \'sha256\':hashlib.sha256((ast.get_source_segment(source,fn) or \'\').encode()).hexdigest(),\n            \'http_markers\':{p:any(p in s for s in strings) for p in (\'/props\',\'/slots\',\'/tokenize\',\'/apply-template\')},\n            \'protocol_keys\':sorted(strings & PROTOCOL),\n            \'assigns_messages\':any(isinstance(n,(ast.Assign,ast.AnnAssign)) and any(\n                isinstance(t,ast.Subscript) and isinstance(t.slice,ast.Constant) and t.slice.value==\'messages\'\n                for t in (n.targets if isinstance(n,ast.Assign) else [n.target])) for n in ast.walk(fn))})\n    return result\n\n\nclass _NoRedirect(urllib.request.HTTPRedirectHandler):\n    def redirect_request(self,*args,**kwargs):raise ValueError(\'NO_REDIRECT\')\n\n\ndef _local(path,data=None):\n    if path not in (\'/props\',\'/apply-template\',\'/tokenize\'):raise ValueError(\'PATH_NOT_READONLY\')\n    raw=None if data is None else json.dumps(data,ensure_ascii=False,separators=(\',\',\':\')).encode()\n    if raw is not None and len(raw)>180000:raise ValueError(\'HTTP_INPUT_LIMIT\')\n    req=urllib.request.Request(\'http://127.0.0.1:8098\'+path,data=raw,\n                              headers={\'Content-Type\':\'application/json\'})\n    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())\n    with opener.open(req,timeout=2) as response:\n        payload=response.read(524289)\n        if len(payload)>524288:raise ValueError(\'HTTP_OUTPUT_LIMIT\')\n        return json.loads(payload)\n\n\ndef _base_tools():\n    tree=ast.parse(_read(ROOT/\'nox_tools.py\').decode())\n    found=[]\n    for node in tree.body:\n        if isinstance(node,ast.Assign) and any(isinstance(n,ast.Name) and n.id==\'TOOLS\' for n in node.targets):\n            found.append(ast.literal_eval(node.value))\n    if len(found)!=1 or not isinstance(found[0],list) or len(found[0])>64:\n        raise ValueError(\'STATIC_TOOLS_UNAVAILABLE\')\n    return found[0]\n\n\ndef inspect_budget(include_token_count=True):\n    started=time.monotonic();result={\'source_bodies_exported\':False,\'native_modules_imported\':False,\n        \'generation_requests\':0,\'metadata\':[]}\n    for name,wanted in (\n        (\'owner_context_budget.py\',{\'trim_messages\',\'context_budget\',\'effective_budget\',\'estimate_tokens\',\'count_tokens\'}),\n        (\'nox_agent_pool_t858u.py\',{\'prepare_payload\'}),\n        (\'chat_proxy.py\',{\'_trim_ctx\',\'_proxy_completion\'})):\n        try:result[\'metadata\'].append(_metadata(ROOT/name,wanted))\n        except Exception as error:result[\'metadata\'].append({\'name\':name,\'unavailable\':type(error).__name__})\n    if include_token_count:\n        try:\n            tools=_base_tools();counts={}\n            names=[str(t.get(\'function\',{}).get(\'name\',\'\')) for t in tools if isinstance(t,dict)]\n            for label,schemas in ((\'plain\',[]),(\'native_base_tools\',tools)):\n                request={\'messages\':[{\'role\':\'user\',\'content\':\'Reply with one short word.\'}],\n                    \'add_generation_prompt\':True,\n                    \'chat_template_kwargs\':{\'enable_thinking\':False,\'thinking_mode\':\'chat\'}}\n                if schemas:request.update(tools=schemas,tool_choice=\'auto\')\n                rendered=_local(\'/apply-template\',request)\n                prompt=rendered.get(\'prompt\')\n                if not isinstance(prompt,str) or len(prompt.encode())>180000:\n                    raise ValueError(\'RENDERED_PROMPT_UNAVAILABLE\')\n                if schemas and not all(name and name in prompt for name in names):\n                    raise ValueError(\'TOOL_RENDER_NOT_VERIFIED\')\n                tokenized=_local(\'/tokenize\',{\'content\':prompt,\'add_special\':False,\'parse_special\':True})\n                ids=tokenized.get(\'tokens\')\n                if not isinstance(ids,list) or len(ids)>50000:raise ValueError(\'TOKEN_COUNT_UNAVAILABLE\')\n                counts[label]={\'tokens\':len(ids),\'rendered_characters\':len(prompt),\'tools\':len(schemas)}\n            result[\'synthetic_token_counts\']=counts\n            result[\'native_base_schema_token_overhead\']=counts[\'native_base_tools\'][\'tokens\']-counts[\'plain\'][\'tokens\']\n            result[\'counts_scope\']=\'BASE_TOOLS_ONLY_NOT_CURRENT_USER_PROMPT_OR_DYNAMIC_EVIDENCE_TOOLS\'\n        except Exception as error:\n            result[\'token_count_unavailable\']=str(error) if re.fullmatch(\'[A-Z_]{1,64}\',str(error)) else type(error).__name__\n    result[\'elapsed_ms\']=round((time.monotonic()-started)*1000)\n    return result\n\n\nCOGNITIVE_MODULES=frozenset((\'nox_brain\',\'nox_cores_t899u\',\'emotion_cedr\',\'infinite_memory\',\n                            \'memory_hooks\',\'s03_memory\',\'runtime_enrich\'))\n\n\ndef inspect_cognitive_sources():\n    """Static call graph only. A present callsite does not prove a live execution."""\n    result={\'runtime_execution_proven\':False,\'native_modules_imported\':False,\n            \'private_source_bodies_exported\':False,\'sources\':[]}\n    for basename in (\'chat_proxy.py\',\'agent_loop.py\'):\n        try:\n            raw=_read(ROOT/basename);tree=ast.parse(raw.decode(\'utf-8\'));aliases={}\n            row={\'name\':basename,\'sha256\':hashlib.sha256(raw).hexdigest(),\'components\':{},\'status_routes\':[]}\n            for node in ast.walk(tree):\n                if isinstance(node,ast.Import):\n                    pairs=[(a.asname or a.name.split(\'.\')[0],a.name) for a in node.names]\n                elif isinstance(node,ast.ImportFrom):\n                    pairs=[(a.asname or a.name,(node.module or \'\')+\'.\'+a.name) for a in node.names]\n                else:continue\n                for alias,full in pairs:\n                    component=full.split(\'.\')[0]\n                    if component in COGNITIVE_MODULES:\n                        aliases[alias]=full\n                        info=row[\'components\'].setdefault(component,{\'import_lines\':[],\'calls\':[]})\n                        info[\'import_lines\'].append(node.lineno)\n            def visit(node,function=\'<module>\',guards=()):\n                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):\n                    function=node.name\n                    for decorator in node.decorator_list:\n                        if (isinstance(decorator,ast.Call) and decorator.args and isinstance(decorator.args[0],ast.Constant)\n                                and isinstance(decorator.args[0].value,str)):\n                            route=decorator.args[0].value\n                            if (re.fullmatch(r\'/api/(?:nox|ui)/[A-Za-z0-9_/-]{1,100}\',route)\n                                    and any(part in route for part in (\'status\',\'memory\',\'brain\',\'core\',\'conscious\',\'emotion\',\'neural\'))):\n                                row[\'status_routes\'].append(route)\n                if isinstance(node,ast.If):\n                    condition=_safe_expr(node.test)\n                    for child in node.body:visit(child,function,(guards+({\'branch\':\'if\',\'condition\':condition},))[-4:])\n                    for child in node.orelse:visit(child,function,(guards+({\'branch\':\'else\',\'condition\':condition},))[-4:])\n                    return\n                if isinstance(node,ast.Call):\n                    name=_name(node.func);first=name.split(\'.\')[0]\n                    if first in aliases:\n                        target=aliases[first]+name[len(first):];component=target.split(\'.\')[0]\n                        calls=row[\'components\'][component][\'calls\']\n                        if len(calls)<32:calls.append({\'function\':function,\'line\':node.lineno,\'call\':target,\'guards\':list(guards)})\n                for child in ast.iter_child_nodes(node):visit(child,function,guards)\n            visit(tree)\n            row[\'status_routes\']=sorted(set(row[\'status_routes\']))[:32]\n            result[\'sources\'].append(row)\n        except Exception as error:result[\'sources\'].append({\'name\':basename,\'unavailable\':type(error).__name__})\n    return result\n\n\n_STATUS_COMPONENTS=frozenset((\'brain\',\'nox_brain\',\'cores\',\'nox_cores\',\'consciousness\',\'self_awareness\',\n                             \'emotion\',\'emotions\',\'cedr\',\'memory\',\'s03\',\'infinite_memory\',\'neural\',\'neural_network\'))\n_STATUS_FIELDS=frozenset((\'enabled\',\'connected\',\'ready\',\'active\',\'healthy\',\'available\',\'state\',\'status\',\n    \'calls\',\'call_count\',\'requests\',\'request_count\',\'processed\',\'successes\',\'errors\',\'error_count\',\n    \'heartbeat_age_seconds\',\'last_success_ts\',\'last_update_ts\',\'total_records\',\'total_items\',\n    \'count\',\'records\',\'creator_messages\',\'retrieval_count\',\'write_count\',\'read_count\'))\n_STATUS_VALUES=frozenset((\'READY\',\'RUNNING\',\'ACTIVE\',\'CONNECTED\',\'ENABLED\',\'DISABLED\',\'IDLE\',\'OFF\',\n                        \'HOLD\',\'UNKNOWN\',\'UNAVAILABLE\',\'DEGRADED\',\'OK\',\'ERROR\'))\n\n\ndef project_cognitive_status(document):\n    """Project only known safe fields from a status body the caller authenticated."""\n    fields={}\n    def visit(value,path=(),in_component=False):\n        if len(path)>5 or not isinstance(value,dict):return\n        for key,item in list(value.items())[:128]:\n            if not isinstance(key,str) or not re.fullmatch(\'[A-Za-z0-9_]{1,64}\',key):continue\n            name=key.lower();component=in_component or name in _STATUS_COMPONENTS\n            current=path+(key,)\n            if component and name in _STATUS_FIELDS:\n                if isinstance(item,(bool,int,float)) and (not isinstance(item,float) or abs(item)<1e100):\n                    fields[\'.\'.join(current)]=item\n                elif isinstance(item,str) and item.upper() in _STATUS_VALUES:\n                    fields[\'.\'.join(current)]=item.upper()\n            if isinstance(item,dict):visit(item,current,component)\n    visit(document)\n    return {\'safe_fields\':fields,\'runtime_counters_available\':any(\n        key.rsplit(\'.\',1)[-1].lower() in (\'calls\',\'call_count\',\'requests\',\'request_count\',\'processed\',\'successes\',\n                                       \'retrieval_count\',\'write_count\',\'read_count\') for key in fields),\n        \'per_turn_execution_proven\':False}\n\n\nif __name__==\'__main__\':\n    print(json.dumps({\'budget\':inspect_budget(),\'cognitive_sources\':inspect_cognitive_sources()},\n                     ensure_ascii=False,separators=(\',\',\':\')))\n', '<reviewed-budget-metadata>', 'exec'), namespace)
    return {'budget':namespace['inspect_budget'](include_token_count=True), 'cognitive_sources':namespace['inspect_cognitive_sources']()}



def cgroup_memory():
    """Three read-only measurements: raw and potential file-cache reclaim are different."""
    root = Path('/sys/fs/cgroup')
    def integer(name):
        raw = bounded(root / name, 4096).decode('ascii').strip()
        if not raw.isdigit():
            raise ValueError('CGROUP_INT_'+name.replace('.', '_').upper())
        return int(raw)
    def fields(name, allow):
        result = {}
        for line in bounded(root / name, 16384).decode('ascii').splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] in allow and parts[1].isdigit():
                result[parts[0]] = int(parts[1])
        return result
    try:
        maximum = integer('memory.max')
        samples = []
        for i in range(3):
            current = integer('memory.current')
            breakdown = fields('memory.stat', {
                'anon', 'file', 'shmem', 'inactive_file', 'active_file',
                'slab_reclaimable', 'slab_unreclaimable', 'kernel', 'file_mapped',
                'file_dirty', 'file_writeback', 'unevictable'})
            events = fields('memory.events', {'low', 'high', 'max', 'oom', 'oom_kill', 'oom_group_kill'})
            pressure = {}
            try:
                for line in bounded(root / 'memory.pressure', 4096).decode('ascii').splitlines():
                    parts = line.split()
                    if parts and parts[0] in ('some', 'full'):
                        pressure[parts[0]] = {
                            key: float(val) for key, val in (p.split('=', 1) for p in parts[1:])
                            if key in ('avg10', 'avg60', 'avg300')}
            except (OSError, ValueError):
                pressure = {'state': 'UNAVAILABLE'}
            # The following is a heuristic estimate, not claimable free RAM.
            # Exclude tmpfs/shmem and dirty/written pages from potential cache.
            cache_candidate = max(0, min(breakdown.get('inactive_file', 0),
                breakdown.get('file', 0) - breakdown.get('shmem', 0)
                - breakdown.get('file_dirty', 0) - breakdown.get('file_writeback', 0)))
            samples.append({'current_bytes': current, 'raw_headroom_bytes': maximum - current,
                'breakdown_bytes': breakdown, 'events': events, 'pressure': pressure,
                'inactive_file_candidate_bytes': cache_candidate,
                'candidate_is_NOT_guaranteed_free': True})
            if i != 2:
                time.sleep(1)
        return {'state': 'READ_ONLY_CGROUP_V2_SAMPLED', 'memory_max_bytes': maximum,
                'samples': samples, 'samples_seconds_apart': 1,
                'reclaim_attempted': False, 'drop_caches_called': False,
                'model_or_services_modified': False}
    except (OSError, ValueError, UnicodeError) as error:
        return {'state': 'UNAVAILABLE', 'reason_type': type(error).__name__,
                'reclaim_attempted': False, 'model_or_services_modified': False}


def dispatcher_diagnostic():
    """Bounded read-only Supervisor classification; never export task/log bodies."""
    report = {'source_imported': False, 'service_restarted': False,
              'log_bodies_exported': False}
    source = ROOT / 'scripts/nox_dispatcher_t855u.py'
    try:
        raw = bounded(source, 1024 * 1024)
        report['script_sha256'] = hashlib.sha256(raw).hexdigest()
        report['script_bytes'] = len(raw)
        ast.parse(raw)
        report['script_syntax'] = 'AST_OK'
    except Exception as error:
        report['script_syntax'] = type(error).__name__
    try:
        config = Path('/etc/supervisor/conf.d/nox-dispatcher-t855u.conf')
        content = bounded(config, 32768).decode('utf-8','replace')
        import configparser
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read_string(content)
        section = 'program:nox-dispatcher-t855u'
        report['config_exists'] = cfg.has_section(section)
        if cfg.has_section(section):
            report['supervisor_settings'] = {
                name: cfg.get(section, name, fallback='UNKNOWN')[:64]
                for name in ('autostart','autorestart','startsecs','startretries')}
            command = cfg.get(section,'command',fallback='')
            import shlex
            argv = shlex.split(command)[:12]
            report['command_basename'] = [os.path.basename(x) for x in argv]
    except Exception as error:
        report['config_error'] = type(error).__name__
    try:
        cmd = subprocess.run(['supervisorctl','tail','-20000',
            'nox-dispatcher-t855u','stderr'],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5,
            env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8'})
        raw = cmd.stdout[-20000:]
        categories = ('Traceback','ModuleNotFoundError','ImportError','NameError',
                      'SyntaxError','IndentationError','AttributeError','ValueError',
                      'OSError','FileNotFoundError','PermissionError','RuntimeError',
                      'MemoryError','OperationalError','Terminated','KeyboardInterrupt')
        report['stderr_tail_rc'] = cmd.returncode
        report['stderr_bytes_sampled'] = len(raw)
        report['error_counts'] = {k: len(re.findall(rb'\b'+k.encode()+rb'\b',raw))
                                  for k in categories if re.search(rb'\b'+k.encode()+rb'\b',raw)}
        report['traceback_present'] = b'Traceback (most recent call last):' in raw
    except Exception as error:
        report['stderr_probe_error'] = type(error).__name__
    return report


def main():
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError()))
    signal.alarm(35)
    report = {'schema': 'NOX_SMART_CHAT_LOCK_PROBE_V1', 'observed_at': time.time(),
              'runtime_modules_imported': False, 'lock_modified': False, 'processes_controlled': False,
              'lock_before': lock_state(), 'files': {name: file_state(path) for name, path in PATHS.items()},
              'services': services(), 'cgroup_memory': cgroup_memory(), 'dispatcher_diagnostic': dispatcher_diagnostic(), 'credential_reader_shape': credential_reader_shape(),
              'cognitive_and_budget': cognitive_and_budget_metadata(),
              'lock_after': lock_state()}
    signal.alarm(0)
    print('NOX_MAINT_INSPECT=' + json.dumps({'kind': 'smart_chat_lock_probe', 'data': report}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_INSPECT_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('NOX_MAINT_INSPECT=' + json.dumps({'kind': 'smart_chat_lock_probe', 'data': {
            'state': 'HOLD_READ_ONLY_PROBE', 'error_type': type(exc).__name__}}, separators=(',', ':')), flush=True)
        raise SystemExit(2)
