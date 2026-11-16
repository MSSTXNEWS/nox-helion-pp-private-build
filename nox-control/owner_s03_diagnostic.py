#!/usr/bin/env python3
"""Metadata-only S03/BGE probe; no memory record, vector or chat text is emitted.

Reads the existing SQLite databases in mode=ro. Does not import memory modules,
create a database/index, load a model, change a service, or call an external API.
The sole embedding request contains two fixed public synthetic strings.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path('/root/nox')
CANONICAL = ROOT / 'kb/knowledge.sqlite'
SOURCE_NAMES = ('s03_memory.py', 'nox_memory.py', 'infinite_memory.py', 'memory_hooks.py', 'nox_cores_t899u.py')
TABLE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,79}$')
PUBLIC_FIXTURES = ['NOX public diagnostic: seventeen times nineteen equals three hundred twenty three.',
                   'NOX public diagnostic: keep verified checkpoints and preserve shared memory.']


class DiagnosticHold(RuntimeError):
    pass


def plain(path):
    path = Path(path)
    # Path.is_relative_to() is lexical: /root/nox/../secret still matches.
    if '..' in path.parts or not path.is_absolute() or not path.is_relative_to(ROOT):
        raise DiagnosticHold('HOLD_S03_PATH_SCOPE')
    for part in (*reversed(path.parents), path):
        try:
            mode = os.lstat(part).st_mode
        except FileNotFoundError:
            # A missing destination is handled by its read/open caller.
            break
        except OSError:
            # Path.is_symlink() may silently return False on EACCES/ELOOP.
            raise DiagnosticHold('HOLD_S03_PATH_UNREADABLE') from None
        if stat.S_ISLNK(mode):
            raise DiagnosticHold('HOLD_S03_SYMLINK')
    return path


def bounded(path, maximum=750000):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise DiagnosticHold('HOLD_S03_FILE_BUDGET')
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise DiagnosticHold('HOLD_S03_FILE_BUDGET')
    return raw


def source_metadata(path):
    raw = bounded(path)
    tree = ast.parse(raw)
    functions, candidates, imports = [], set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
                'recall', 'remember', 'init_db', 'persist_turn', 'format_for_prompt', 'counts', 'status', 'search'):
            functions.append({'name': node.name, 'arguments': [x.arg for x in node.args.args],
                              'line': node.lineno, 'end_line': node.end_lineno})
        if isinstance(node, ast.Import):
            imports.update(alias.name.split('.')[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split('.')[0])
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) <= 300:
            value = Path(node.value)
            if value.is_absolute() and value.is_relative_to(ROOT) and value.suffix in ('.db', '.sqlite', '.sqlite3'):
                candidates.add(value)
    # Only technical booleans: no string literals or memory initialization text.
    text = raw.decode('utf-8')
    return {'module': path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'functions': functions,
            'uses_sqlite': 'sqlite3' in imports, 'uses_faiss': 'faiss' in imports,
            'mentions_embedding_endpoint': '/v1/embeddings' in text,
            'mentions_s03_vector_table': bool(re.search(r's03_(?:embeddings|vectors|semantic)', text)),
            'mentions_lexical_match': 's03_fts MATCH' in text,
            'mentions_rerank_8098': '127.0.0.1:8098' in text,
            'source_body_exported': False}, candidates


def schema_probe(path, deadline):
    result = {'database_role': 'CANONICAL_S03' if path == CANONICAL else 'LEGACY_CANDIDATE',
              'path': str(path), 'record_text_exported': False, 'state': 'ABSENT'}
    db = None
    try:
        path = plain(path)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise DiagnosticHold('HOLD_S03_NOT_REGULAR_DATABASE')
        result.update(bytes=info.st_size, device=info.st_dev, inode=info.st_ino)
        db = sqlite3.connect('file:' + urllib.parse.quote(str(path), safe='/') + '?mode=ro', uri=True, timeout=.15)
        db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA busy_timeout=150')
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        rows = db.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name LIMIT 81").fetchall()
        tables = []
        names = set()
        for name, kind in rows[:80]:
            if not TABLE.fullmatch(name) or re.search(r'(?i)(?:hf_|ghp_|github_pat_|sk-)', name):
                continue
            names.add(name)
            if name.startswith('sqlite_') or re.search(r'_(?:data|idx|docsize|config|content)$', name) and name.startswith('s03_fts'):
                continue
            columns = [{'name': row[1], 'type': row[2], 'primary_key': bool(row[5])}
                       for row in db.execute('PRAGMA table_info("' + name + '")').fetchall()[:64]
                       if TABLE.fullmatch(row[1]) and len(row[2]) <= 64]
            table = {'name': name, 'type': kind, 'columns': columns}
            if kind == 'table' and time.monotonic() < deadline:
                try:
                    table['row_count'] = db.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                except sqlite3.Error:
                    table['count_state'] = 'BOUNDED_QUERY_UNAVAILABLE'
            tables.append(table)
        result.update(state='SCHEMA_OBSERVED', tables=tables, schema_truncated=len(rows) > 80,
                      has_s03_items='s03_items' in names, has_s03_fts='s03_fts' in names,
                      has_docs_chunks={'docs', 'chunks'} <= names,
                      possible_vector_tables=[n for n in sorted(names) if re.search(r'(?i)(?:vector|embedding|semantic)', n)])
        if 's03_items' in names and time.monotonic() < deadline:
            columns = {r[1] for r in db.execute('PRAGMA table_info(s03_items)')}
            if {'segment', 'text'} <= columns:
                groups = db.execute('SELECT segment,count(*) FROM s03_items GROUP BY segment').fetchall()
                result['segments'] = {key: count for key, count in groups if re.fullmatch(r'M[0-7]', str(key))}
                result['other_segment_count'] = sum(count for key, count in groups if not re.fullmatch(r'M[0-7]', str(key)))
                sizes = db.execute('SELECT count(*),coalesce(sum(length(text)),0),coalesce(max(length(text)),0) FROM s03_items').fetchone()
                result['s03_size_metadata'] = dict(zip(('rows', 'text_characters_total', 'text_characters_max'), sizes))
                quotas = {'M7': 3, 'M5': 2, 'M0': 2, 'M6': 2, 'M2': 2, 'M3': 2, 'M4': 1}
                result['legacy_pin_rows_possible'] = sum(min(result['segments'].get(key, 0), value) for key, value in quotas.items())
                result['legacy_chat_return_limit_k6'] = 10
                result['legacy_pins_can_fill_all_chat_results'] = result['legacy_pin_rows_possible'] >= 10
            if {'id', 'sha256'} <= columns:
                result['s03_hash_missing_count'] = db.execute("SELECT count(*) FROM s03_items WHERE sha256 IS NULL OR length(sha256)<>64").fetchone()[0]
        result['schema_read_only'] = True
    except FileNotFoundError:
        pass
    except (OSError, sqlite3.Error, DiagnosticHold) as exc:
        result.update(state='BOUNDED_SCHEMA_UNAVAILABLE', error_class=type(exc).__name__)
    finally:
        if db is not None:
            db.close()
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise DiagnosticHold('HOLD_EMBEDDING_REDIRECT')


def local_json(path, data=None, timeout=4):
    if path not in ('/health', '/v1/models', '/v1/embeddings'):
        raise DiagnosticHold('HOLD_EMBEDDING_PATH')
    raw = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request('http://127.0.0.1:8082' + path, data=raw,
                                     headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        value = response.read(300001)
        if len(value) > 300000:
            raise DiagnosticHold('HOLD_EMBEDDING_RESPONSE_BUDGET')
        return response.status, json.loads(value)


def embedding_probe():
    result = {'state': 'UNVERIFIED', 'port': 8082, 'private_text_submitted': False,
              'synthetic_inputs': len(PUBLIC_FIXTURES), 'model_loaded_by_probe': False, 'vectors_exported': False}
    started = time.monotonic()
    try:
        health, _ = local_json('/health', timeout=2)
        if health != 200:
            raise DiagnosticHold('HOLD_EMBEDDING_HEALTH_HTTP')
        result['health_http'] = health
        code, models = local_json('/v1/models', timeout=2)
        if code != 200 or not isinstance(models, dict):
            raise DiagnosticHold('HOLD_EMBEDDING_MODELS_HTTP')
        ids = [r.get('id') for r in models.get('data', []) if isinstance(r, dict) and isinstance(r.get('id'), str)]
        result.update(model_http=code, model_count=len(ids), model_id_contains_bge=any('bge' in value.lower() for value in ids))
        code, response = local_json('/v1/embeddings', {'model': 'bge-m3', 'input': PUBLIC_FIXTURES}, timeout=5)
        if code != 200 or not isinstance(response, dict):
            raise DiagnosticHold('HOLD_EMBEDDING_BATCH_HTTP')
        rows = response.get('data')
        if not isinstance(rows, list) or len(rows) != len(PUBLIC_FIXTURES):
            raise DiagnosticHold('HOLD_EMBEDDING_BATCH_SHAPE')
        dimensions, norms = [], []
        for row in rows:
            vector = row.get('embedding') if isinstance(row, dict) else None
            if (not isinstance(vector, list) or not 32 <= len(vector) <= 8192
                    or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)):
                raise DiagnosticHold('HOLD_EMBEDDING_VECTOR_SHAPE')
            norm = math.sqrt(sum(value * value for value in vector))
            if not math.isfinite(norm) or norm <= 0:
                raise DiagnosticHold('HOLD_EMBEDDING_VECTOR_NORM')
            dimensions.append(len(vector)); norms.append(round(norm, 6))
        if len(set(dimensions)) != 1:
            raise DiagnosticHold('HOLD_EMBEDDING_DIMENSION_MISMATCH')
        result.update(state='SYNTHETIC_EMBEDDING_BATCH_VERIFIED', http=code,
                      dimensions=dimensions[0], rows=len(rows), vector_norms=norms,
                      semantic_retrieval_quality='NOT_MEASURED_BY_ENDPOINT_PROBE')
    except (OSError, ValueError, DiagnosticHold, KeyError, TypeError) as exc:
        result.update(state='EMBEDDING_PROBE_UNAVAILABLE', error_class=type(exc).__name__)
    result['seconds'] = round(time.monotonic() - started, 4)
    return result


def run():
    start = time.monotonic()
    end = start + 18
    sources, candidates = [], {CANONICAL}
    for name in SOURCE_NAMES:
        try:
            metadata, paths = source_metadata(ROOT / 'scripts' / name)
            sources.append(metadata); candidates.update(paths)
        except (OSError, SyntaxError, ValueError, DiagnosticHold) as exc:
            sources.append({'module': name, 'state': 'SOURCE_UNAVAILABLE', 'error_class': type(exc).__name__})
    candidates.update(ROOT / ('memory/cores/C%02d/ltm.sqlite' % n) for n in range(1, 13))
    databases = []
    for path in [CANONICAL] + [p for p in sorted(candidates) if p != CANONICAL][:16]:
        if time.monotonic() > end - 9:
            break
        databases.append(schema_probe(path, min(end - 9, time.monotonic() + (2 if path == CANONICAL else .35))))
    faiss = {'index_present': False, 'ids_exported': False}
    try:
        index = plain(ROOT / 'kb/faiss.index').stat()
        faiss.update(index_present=stat.S_ISREG(index.st_mode), index_bytes=index.st_size)
        metadata = json.loads(bounded(ROOT / 'kb/faiss_meta.json', 4 * 1024 * 1024))
        ids = metadata.get('ids')
        if isinstance(ids, list):
            faiss['id_count'] = len(ids)
        faiss['coverage'] = 'LEGACY_DOCS_CHUNKS_INDEX_S03_COVERAGE_NOT_PROVEN'
    except (OSError, ValueError, DiagnosticHold):
        pass
    embeddings = embedding_probe()
    versions = {}
    for name in ('numpy', 'faiss-cpu', 'sqlite-vec'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    current = next((r for r in databases if r['database_role'] == 'CANONICAL_S03'), {})
    count = (current.get('s03_size_metadata') or {}).get('rows')
    dimension = embeddings.get('dimensions')
    return {'schema': 'NOX_OWNER_S03_DIAGNOSTIC_V1', 'state': 'BOUNDED_DIAGNOSTIC_COMPLETE',
            'sources': sources, 'databases': databases, 'legacy_candidate_count': len(candidates) - 1,
            'legacy_candidates_inspected': max(0, len(databases) - 1), 'faiss': faiss,
            'embedding_endpoint': embeddings, 'current_interpreter_packages': versions,
            's03_float32_vector_payload_estimate_bytes': count * dimension * 4 if type(count) is int and type(dimension) is int else None,
            'new_vectors_indexed': 0, 'memory_records_merged': 0, 'database_mutated': False,
            'private_record_text_exported': False, 'embedding_model_duplicated': False,
            'seconds': round(time.monotonic() - start, 4)}


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not request.isdigit() or len(request) > 20 or not re.fullmatch(r'[0-9a-f]{40}', source):
        raise DiagnosticHold('HOLD_OWNER_CONTEXT')
    result = run()
    result.update(request=request, source_sha=source)
    path = plain(ROOT / 'state' / ('owner_s03_diagnostic_' + request + '.json'))
    if path.exists():
        raise DiagnosticHold('HOLD_DIAGNOSTIC_ALREADY_RECORDED')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(result, stream, ensure_ascii=True); stream.flush(); os.fsync(stream.fileno())
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 's03_semantic_diagnostic', 'data': result}, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    main()
