"""Exact-CAS additive transform; private native bridge bytes never leave the host.

The new table is received-goal context, not a scheduler, execution ledger or tool
replay queue. Existing native authentication, STOP, history and S03 proof remain.
"""
from __future__ import annotations

import ast
import hashlib

SOURCE_SHA256 = '9d7475428ad8c553c756ca50280ac2363e7c03854abab285de560ae066d4586a'
FUNCTION_SHA256 = {
    '_dialog_context': '8a8ea53bbfa4d03f5e551ac674eb456c499c5bd0c850fe78983f896202ead74c',
    'resonance_v24_chat': 'e5cc8ccf79799f0d449c4d6adb3dee07848e8a338caa3bf4bf0d1e0c006d4172',
    'native_v29_stream': '064ef9a8a3d6752d47494e9b8060e08dcbbc85da9ab30e5a504203b3e7fa794d',
}
MARKER = '# NOX_RECEIVED_GOAL_CONTEXT_V1'

HELPERS = r'''

# NOX_RECEIVED_GOAL_CONTEXT_V1
# Only authenticated native routes call these seams, after original dialog scope
# verification. A failed turn stays RECEIVED. No tools or inference are replayed.
_NOX_PENDING_SCHEMA = """
CREATE TABLE IF NOT EXISTS nox_chat_received_goals (
 row_id INTEGER PRIMARY KEY AUTOINCREMENT,
 owner TEXT NOT NULL, dialog_id TEXT NOT NULL, request_id TEXT NOT NULL,
 client_request_id TEXT, goal_request_id TEXT NOT NULL,
 continuation_kind TEXT NOT NULL CHECK(continuation_kind IN ('GOAL','CONTINUE','SCOPE','ATTENTION')),
 question TEXT NOT NULL, question_sha256 TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RECEIVED','RESPONSE_COMMITTED')),
 received_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 resolved_by_request_id TEXT, s03_record_id TEXT, s03_sha256 TEXT,
 UNIQUE(owner,dialog_id,request_id),
 FOREIGN KEY(dialog_id) REFERENCES nox_v29_dialogs(dialog_id)
);
CREATE INDEX IF NOT EXISTS nox_chat_received_goal_pending
 ON nox_chat_received_goals(owner,dialog_id,row_id DESC)
 WHERE state='RECEIVED' AND request_id=goal_request_id AND continuation_kind!='ATTENTION';
CREATE INDEX IF NOT EXISTS nox_chat_received_goal_scope
 ON nox_chat_received_goals(owner,dialog_id,goal_request_id,row_id DESC)
 WHERE continuation_kind='SCOPE';
"""
_NOX_PENDING_CONTINUE = re.compile(
 r'^\s*(?:(?:да|хорошо|ок|ладно|пожалуйста)[\s,!.:;-]+)*'
 r'(?:делай|сделай|продолж\w*|продоли\w*|додел\w*|доведи|заверш\w*|'
 r'возобнов\w*|повтори|выполн\w*|исправ\w*|сохрани(?:ть)?\s+(?:этот\s+)?алгоритм|'
 r'всех\s+доступных\s+учител\w*|все\s+доступные\s+учител\w*|'
 r'continue|resume|finish|do\s+it)(?:\b|[.!?,:;\s])', re.I)
_NOX_PENDING_ATTENTION = re.compile(
 r'^\s*(?:ау+|ал+о+|эй|ну|да|ок|хорошо|ты\s+(?:тут|здесь)|где\s+ответ|'
 r'что\s+там|всё\s+ещё\s+жду|жду|[?…]+)[\s?!.…]*$', re.I)
_NOX_PENDING_SCOPE = re.compile(
 r'^\s*(?:ко?\s+всем|для\s+всех|на\s+все|по\s+всем|во\s+всех|'
 r'всех|все|только|именно|и\s+(?:ещё|также)|а\s+(?:ещё|также))\b', re.I)

def _nox_pending_context(dialog_id, question, request_id, client_request_id=None):
    """Persist the received instruction and return at most one same-dialog goal."""
    question = question.strip() if isinstance(question,str) else ''
    if not question or len(question)>8000 or not re.fullmatch('[a-f0-9]{32}',request_id):
        raise RuntimeError('HOLD_RECEIVED_GOAL_INPUT')
    if not isinstance(client_request_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',client_request_id):
        client_request_id = None
    sha = hashlib.sha256(question.encode('utf-8')).hexdigest()
    with _db(True) as db:
        found = _get_dialog(db,dialog_id)
        if found is None or bool(found['archived']):
            raise RuntimeError('HOLD_RECEIVED_GOAL_SCOPE')
        db.executescript(_NOX_PENDING_SCHEMA)
        db.execute('BEGIN IMMEDIATE')
        prior = None
        kind = ('ATTENTION' if _NOX_PENDING_ATTENTION.match(question) else
                'SCOPE' if _NOX_PENDING_SCOPE.match(question) else
                'CONTINUE' if _NOX_PENDING_CONTINUE.match(question) else 'GOAL')
        if kind!='GOAL':
            prior = db.execute(
                "SELECT request_id,substr(question,1,8001) AS question,question_sha256 FROM nox_chat_received_goals "
                "WHERE owner=? AND dialog_id=? AND state='RECEIVED' "
                "AND request_id=goal_request_id AND continuation_kind!='ATTENTION' ORDER BY row_id DESC LIMIT 1",
                (OWNER,dialog_id)).fetchone()
        goal_id = prior['request_id'] if prior else request_id
        stamp = _now()
        db.execute(
            'INSERT INTO nox_chat_received_goals '
            '(owner,dialog_id,request_id,client_request_id,goal_request_id,continuation_kind,question,'
            'question_sha256,state,received_at,updated_at) VALUES(?,?,?,?,?,?,?,?,\'RECEIVED\',?,?)',
            (OWNER,dialog_id,request_id,client_request_id,goal_id,kind,question,sha,stamp,stamp))
        if prior and kind!='ATTENTION':
            previous = prior['question']
            if (not isinstance(previous,str) or not 1<=len(previous)<=8000 or
                    hashlib.sha256(previous.encode('utf-8')).hexdigest()!=prior['question_sha256']):
                raise RuntimeError('HOLD_RECEIVED_GOAL_CONTENT')
            # Preserve the latest three scope clarifications across failed
            # attempts. Ping/acknowledgement turns never become a new goal and
            # never authorize or complete the earlier work.
            qualifiers = db.execute(
                'SELECT substr(question,1,8001) AS question,question_sha256 FROM nox_chat_received_goals '
                "WHERE owner=? AND dialog_id=? AND goal_request_id=? AND continuation_kind='SCOPE' "
                'AND request_id!=? ORDER BY row_id DESC LIMIT 3',
                (OWNER,dialog_id,goal_id,request_id)).fetchall()
            result = [previous]
            for qualifier in reversed(qualifiers):
                value = qualifier['question']
                if (not isinstance(value,str) or not 1<=len(value)<=8000 or
                        hashlib.sha256(value.encode('utf-8')).hexdigest()!=qualifier['question_sha256']):
                    raise RuntimeError('HOLD_RECEIVED_GOAL_CONTENT')
                if value not in result:
                    result.append(value)
            return result
    return []

def _nox_pending_dialog_context(dialog_id, question, request_id, client_request_id=None):
    issue, history = _dialog_context(dialog_id)
    if issue:
        return issue, history
    previous = _nox_pending_context(dialog_id,question,request_id,client_request_id)
    # A real, previously received user instruction is context. Do not fabricate
    # an assistant success or imply the earlier tool effects were rolled back.
    history = list(history)
    for content in previous:
        if content!=question.strip() and not any(m.get('role')=='user' and m.get('content','').strip()==content for m in history):
            history.append({'role':'user','content':content})
    return issue, history

def _nox_pending_save_exchange(dialog_id, question, answer, exchange_id, request_id):
    if not _save_exchange(dialog_id,question,answer,exchange_id):
        return False
    if not dialog_id:
        return True
    try:
        with _db(True) as db:
            # Verify the original S03 proof and exact committed dialog pair.
            # Completion of a reply is not proof that arbitrary tools succeeded.
            proof = db.execute('SELECT sha256 FROM s03_items WHERE id=? LIMIT 1',
                               (exchange_id,)).fetchone()
            pair = db.execute('SELECT role,content FROM nox_v29_dialog_messages '
                'WHERE dialog_id=? AND exchange_id=? LIMIT 3',(dialog_id,exchange_id)).fetchall()
            expected = {'user':question,'assistant':answer}
            if (proof is None or not re.fullmatch('[a-fA-F0-9]{64}',str(proof['sha256'])) or
                    len(pair)!=2 or {row['role']:row['content'] for row in pair}!=expected):
                return False
            row = db.execute('SELECT question,goal_request_id,continuation_kind FROM nox_chat_received_goals '
                'WHERE owner=? AND dialog_id=? AND request_id=? LIMIT 1',
                (OWNER,dialog_id,request_id)).fetchone()
            if row is None or row['question']!=question.strip():
                return False
            # Only the current request and its single root goal change state.
            # Intermediate failed continuations keep their original evidence.
            db.execute("UPDATE nox_chat_received_goals SET state='RESPONSE_COMMITTED',"
                'updated_at=?,resolved_by_request_id=?,s03_record_id=?,s03_sha256=? '
                "WHERE owner=? AND dialog_id=? AND request_id IN (?,?) AND state='RECEIVED'",
                (_now(),request_id,exchange_id,proof['sha256'],OWNER,dialog_id,
                 request_id,row['goal_request_id'] if row['continuation_kind']!='ATTENTION' else request_id))
        return True
    except (OSError,RuntimeError,sqlite3.Error,ValueError,TypeError):
        return False
'''


def _source_span(lines, node):
    """AST columns are UTF-8 byte offsets, so never use Unicode string slicing."""
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    return (starts[node.lineno-1] + node.col_offset,
            starts[node.end_lineno-1] + node.end_col_offset)


def _splice(source, route_names):
    text = source.decode('utf-8')
    tree = ast.parse(text)
    lines = source.splitlines(keepends=True)
    nodes = {name:[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                   and n.name==name] for name in route_names}
    patches = []
    for name in route_names:
        if len(nodes[name])!=1:
            raise ValueError('HOLD_RECEIVED_GOAL_ROUTE_SEAM')
        node = nodes[name][0]
        if not isinstance(node,ast.AsyncFunctionDef):
            raise ValueError('HOLD_RECEIVED_GOAL_ROUTE_ASYNC')
        body = node.body[1:] if isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str) else node.body
        start,_ = _source_span(lines,body[0])
        indent = b' ' * body[0].col_offset
        # The local identity exists before any early return; it does no I/O and
        # is inherited by the route's eventual streaming generator closure.
        patches.append((start,start,b'_nox_received_request_id = uuid.uuid4().hex\n'+indent))
        counts = {'_dialog_context':0,'_save_exchange':0}
        for call in ast.walk(node):
            if not isinstance(call,ast.Call):
                continue
            threaded = (isinstance(call.func,ast.Attribute) and call.func.attr=='to_thread'
                        and call.args and isinstance(call.args[0],ast.Name))
            called = call.args[0].id if threaded else call.func.id if isinstance(call.func,ast.Name) else None
            if called not in counts:
                continue
            args = list(call.args[1:] if threaded else call.args)
            if call.keywords or len(args)!=(1 if called=='_dialog_context' else 4):
                raise ValueError('HOLD_RECEIVED_GOAL_ARGUMENT_SEAM')
            counts[called]+=1
            replacement = ast.parse(ast.unparse(call),mode='eval').body
            target = '_nox_pending_dialog_context' if called=='_dialog_context' else '_nox_pending_save_exchange'
            if threaded:
                replacement.args[0]=ast.Name(id=target,ctx=ast.Load())
            else:
                replacement.func=ast.Name(id=target,ctx=ast.Load())
            extra = ("data.get('message'), _nox_received_request_id, data.get('request_id')"
                     if called=='_dialog_context' else '_nox_received_request_id')
            replacement.args.extend(ast.parse('f('+extra+')',mode='eval').body.args)
            a,b = _source_span(lines,call)
            patches.append((a,b,ast.unparse(replacement).encode('utf-8')))
        if counts!={'_dialog_context':1,'_save_exchange':1}:
            raise ValueError('HOLD_RECEIVED_GOAL_CALL_COUNT')
    for start,end,replacement in sorted(patches,reverse=True):
        source=source[:start]+replacement+source[end:]
    result=source+HELPERS.encode('utf-8')
    compile(result,'<native-bridge-received-goal>','exec')
    return result


def transform(source: bytes) -> bytes:
    if not isinstance(source,bytes) or hashlib.sha256(source).hexdigest()!=SOURCE_SHA256:
        raise ValueError('HOLD_RECEIVED_GOAL_SOURCE_CAS')
    text=source.decode('utf-8')
    if MARKER in text or 'owner_chat_request_ledger' in text:
        raise ValueError('HOLD_RECEIVED_GOAL_EXISTING_LEDGER')
    tree=ast.parse(text)
    for name,expected in FUNCTION_SHA256.items():
        found=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
        if len(found)!=1 or hashlib.sha256(ast.get_source_segment(text,found[0]).encode('utf-8')).hexdigest()!=expected:
            raise ValueError('HOLD_RECEIVED_GOAL_FUNCTION_CAS')
    return _splice(source,('resonance_v24_chat','native_v29_stream'))
