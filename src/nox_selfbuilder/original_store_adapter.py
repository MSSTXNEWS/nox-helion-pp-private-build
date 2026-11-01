"""P02 projection of the ORIGINAL S03/CoreRuntime SQLite schema.

OneHostStoreActor owns the original Store and sole SQLite connection. Reuse the
original CoreRuntime schema migration/read helpers without constructing another
runtime, transport or database. Existing legacy rows are never reassigned to a
new authenticated principal. No model weights or optimizer files are written.
"""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
from types import SimpleNamespace
import uuid

from .onehost_store import OneHostStoreActor, StoreActorHold
from .seed import attest_seed

_MODEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}\Z')


class OriginalStoreChatAdapter:
    def __init__(self, actor: OneHostStoreActor, *, seed_archive=None):
        if not isinstance(actor, OneHostStoreActor):
            raise TypeError('ORIGINAL_STORE_ACTOR_REQUIRED')
        self.actor = actor
        self.seed_archive = Path(seed_archive) if seed_archive is not None else None
        self._generation = ContextVar('nox_original_store_generation', default=None)
        self.actor.call(self._initialize)

    @staticmethod
    def _initialize(store):
        from helion.storage import Store
        from helion.ai_core_runtime import CoreRuntime
        if not isinstance(store, Store):
            raise StoreActorHold('ORIGINAL_HELION_STORE_REQUIRED')
        if store.conn.in_transaction:
            raise StoreActorHold('ORIGINAL_STORE_TRANSACTION_ACTIVE')
        @contextmanager
        def connection():
            with store.conn:
                yield store.conn
        # Execute the canonical migration on the sole actor-owned connection.
        CoreRuntime._init_db(SimpleNamespace(_sqlite_lock=Lock(), _connection=connection))
        return True

    @staticmethod
    def resolve_chat_id(core_id=None, persona_id=None):
        from helion.contracts import CORE_IDS
        from helion.personas import persona_chat_id
        core_id = 'core.core' if core_id is None else core_id
        if core_id not in CORE_IDS:
            raise PermissionError('UNKNOWN_ORIGINAL_CORE_ID')
        persona_chat = persona_chat_id(persona_id)
        if core_id == 'core.core' and persona_id is None:
            return 'default'
        return 'nox_' + core_id.removeprefix('core.') + '_' + persona_chat

    @classmethod
    def _scope(cls, tenant, principal, chat_id):
        from helion.contracts import CORE_IDS
        from helion.personas import PERSONAS, persona_chat_id
        if any(type(v) is not str or not 1 <= len(v) <= 128 or
               any(ord(c) < 32 for c in v) for v in (tenant, principal, chat_id)):
            raise PermissionError('NATIVE_MEMORY_SCOPE_REQUIRED')
        found = None
        for core in CORE_IDS:
            for persona in (None, *(p.persona_id for p in PERSONAS)):
                if cls.resolve_chat_id(core, persona) == chat_id:
                    found = (core, persona_chat_id(persona))
                    break
            if found is not None:
                break
        if found is None:
            raise PermissionError('UNKNOWN_NATIVE_CHAT_SCOPE')
        # Original schema lacks tenant/user columns. Stable native project scope
        # prevents principal collisions without reattributing legacy rows.
        principal_scope = json.dumps([tenant, principal], ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')
        project = 'u' + hashlib.sha256(principal_scope).hexdigest()[:63]
        return project, found[0], found[1]

    @contextmanager
    def model_context(self, model_id):
        if type(model_id) is not str or not _MODEL.fullmatch(model_id):
            raise ValueError('ACTUAL_LOCAL_MODEL_ID_REQUIRED')
        token = self._generation.set({'model_id': model_id, 'epochs': {}})
        try:
            yield self
        finally:
            self._generation.reset(token)

    def history(self, tenant, principal, chat_id, limit=100):
        from helion.ai_core_runtime import CoreRuntime
        if type(limit) is not int or not 1 <= limit <= 250:
            raise ValueError('BOUNDED_HISTORY_REQUIRED')
        project, core, chat = scope = self._scope(tenant, principal, chat_id)
        def read(store):
            if store.conn.in_transaction:
                raise StoreActorHold('ORIGINAL_STORE_TRANSACTION_ACTIVE')
            store.conn.execute('BEGIN')
            try:
                rows = CoreRuntime._history_rows(store.conn, core, project, chat, (limit + 1) // 2)
                epoch = CoreRuntime._history_epoch_in(store.conn, project, core, chat)
                return {'rows': rows, 'epoch': epoch}
            finally:
                store.conn.rollback()
        result = self.actor.call(read)
        generation = self._generation.get()
        if generation is not None:
            generation['epochs'][scope] = result['epoch']
        messages = []
        for row in reversed(result['rows']):
            messages.extend(({'role': 'user', 'content': row['prompt']},
                             {'role': 'assistant', 'content': row['response']}))
        return messages[-limit:]

    def add_exchange(self, tenant, principal, chat_id, prompt, answer, *, authorize):
        from helion.ai_core_runtime import CoreRuntime
        if not callable(authorize):
            raise PermissionError('NATIVE_CHAT_AUTHORIZATION_REQUIRED')
        if (type(prompt) is not str or not 1 <= len(prompt) <= 8000 or
                type(answer) is not str or len(answer) > 65536):
            raise ValueError('ORIGINAL_CHAT_BOUNDS_REQUIRED')
        project, core, chat = scope = self._scope(tenant, principal, chat_id)
        generation = self._generation.get()
        if generation is None or scope not in generation['epochs']:
            raise StoreActorHold('MODEL_AND_HISTORY_CONTEXT_REQUIRED')
        model = generation['model_id']; epoch = generation['epochs'][scope]
        request_id = uuid.uuid4().hex
        def persist(store):
            authorize()
            if store.conn.in_transaction:
                raise StoreActorHold('ORIGINAL_STORE_TRANSACTION_ACTIVE')
            with store.conn:
                store.conn.execute('BEGIN IMMEDIATE')
                if CoreRuntime._history_epoch_in(store.conn, project, core, chat) != epoch:
                    raise PermissionError('ORIGINAL_HISTORY_CONTEXT_REVOKED')
                authorize()
                store.conn.execute('''INSERT INTO core_chat_turns
                    (project_id,core_id,chat_id,request_id,model_id,user_prompt,model_reply)
                    VALUES(?,?,?,?,?,?,?)''', (project, core, chat, request_id, model, prompt, answer))
                store._audit('P02_CHAT_EXCHANGE_SAVED', 0,
                             {'request_id': request_id, 'project_id': project,
                              'core_id': core, 'chat_id': chat, 'model_id': model})
                authorize()
            return request_id
        return self.actor.call(persist)

    def add_message(self, *_args, **_kwargs):
        raise StoreActorHold('ATOMIC_ORIGINAL_EXCHANGE_REQUIRED')

    def store_file(self, *_args, **_kwargs):
        raise StoreActorHold('ORIGINAL_ATTACHMENT_PORT_NOT_BOUND')

    def lineage_status(self):
        try:
            if self.seed_archive is None:
                raise FileNotFoundError('SEED_ARCHIVE_NOT_CONFIGURED')
            seed = attest_seed(self.seed_archive)
        except (OSError, ValueError, KeyError, TypeError):
            return {'S03': 'ORIGINAL_STORE_READY', 'SEED': 'SEED_LINEAGE_HOLD',
                    'weights_changed': False, 'native_acceptance': False}
        return {'S03': 'ORIGINAL_STORE_READY', 'SEED': seed['status'],
                'seed_archive_sha256': seed['archive_sha256'],
                'optimizer_sha256': seed['optimizer_sha256'],
                'weights_changed': False, 'native_acceptance': False}

    def ingest_verified_knowledge(self, tenant, principal, chat_id, *, evidence, text,
                                  authorize, stopped, find_saved, write_saved):
        """Admit reviewed DATA to the native S03 owner, never create a second DB.
        The OneHost caller binds its existing original-S03 find/write primitives.
        This method does not claim a backend exists merely because a callback
        was supplied; it requires transactional readback before returning ACK.
        """
        project, core, chat = self._scope(tenant, principal, chat_id)
        if (type(evidence) is not dict or
                evidence.get('status') != 'NATIVE_S03_RIGHTS_REVIEWED' or
                evidence.get('owner_consented') is not True or
                type(evidence.get('source_sha256')) is not str or
                not re.fullmatch(r'[0-9a-f]{64}', evidence['source_sha256']) or
                type(evidence.get('text_sha256')) is not str or
                not re.fullmatch(r'[0-9a-f]{64}', evidence['text_sha256']) or
                type(evidence.get('rights_receipt_id')) is not str or
                not re.fullmatch(r'[A-Za-z0-9._:-]{8,128}', evidence['rights_receipt_id']) or
                type(text) is not str or not 1 <= len(text.encode('utf-8')) <= 16384 or
                '\x00' in text or
                hashlib.sha256(text.encode('utf-8')).hexdigest() != evidence['text_sha256']):
            raise StoreActorHold('S03_VERIFIED_CONTENT_OR_RIGHTS_REQUIRED')
        if not all(callable(x) for x in (authorize, stopped, find_saved, write_saved)):
            raise StoreActorHold('S03_NATIVE_OWNER_CALLBACKS_REQUIRED')
        record = {'project_id': project, 'core_id': core, 'chat_id': chat,
                  'source_sha256': evidence['source_sha256'],
                  'text_sha256': evidence['text_sha256'],
                  'rights_receipt_id': evidence['rights_receipt_id'],
                  'content': text}
        def require_live_permission():
            if authorize() is not True or stopped() is not False:
                raise PermissionError('S03_INGEST_REVOKED_OR_STOPPED')
        require_live_permission()
        def ingest(store):
            require_live_permission()
            if store.conn.in_transaction:
                raise StoreActorHold('ORIGINAL_STORE_TRANSACTION_ACTIVE')
            with store.conn:
                store.conn.execute('BEGIN IMMEDIATE')
                before = find_saved(store, record)
                if before is None:
                    require_live_permission()
                    write_saved(store, record)
                elif type(before) is not dict:
                    raise StoreActorHold('S03_NATIVE_READBACK_SCHEMA_HOLD')
                saved = find_saved(store, record)
                if type(saved) is not dict or any(
                        saved.get(key) != record[key] for key in
                        ('project_id', 'core_id', 'chat_id', 'source_sha256',
                         'text_sha256', 'rights_receipt_id', 'content')):
                    raise StoreActorHold('S03_NATIVE_READBACK_MISMATCH')
                require_live_permission()  # STOP or ACL change rolls back INSERT.
            return {'state': 'S03_COMMITTED_READBACK' if before is None else
                    'S03_DEDUPLICATED_READBACK',
                    'source_sha256': record['source_sha256'],
                    'text_sha256': record['text_sha256'],
                    'rights_receipt_id': record['rights_receipt_id'],
                    'native_acceptance': False, 'weights_updated': False}
        return self.actor.call(ingest)

    def assert_model_switch_safe(self):
        status = self.lineage_status()
        if status['SEED'] == 'SEED_LINEAGE_HOLD':
            raise StoreActorHold('SEED_LINEAGE_HOLD')
        return status
