"""NOX V16 E06 · one native P02 on the EXACT ORIGINAL helion.sqlite3.

No other database, WebView, Python process or CoreRuntime history. Original
729 source is never modified; T06 stages this into a disposable verified copy.
Only the canonical WPF authenticated SID/ACL/consent host may launch this mode.
Windows E2E/installed model acceptance remains separate from source tests.
"""
from __future__ import annotations
import getpass
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

from nox_native_bridge import (
    NoxPackHost, NativeSession, BoundPort, APPROVED_NATIVE_POLICY,
    ExistingP02Adapter,
)
from p02_native_ingress import NativeIngress
from p02_framed_worker import serve_native_frames
from p02_runtime import P02Store, OllamaClient
from .local_model import discover_installed_local_models

# Exact original Store V4 object names, captured from the approved
# ff8e2848... 729-member original archive. Fail on unrecognized schema.
ORIGINAL_V4_OBJECTS = frozenset((
    "approved_examples", "audit", "e03_core_memories",
    "e03_core_memory_audit", "evolution_cards", "evolution_cases",
    "evolution_policy", "evolution_policy_history", "evolution_trials",
    "ix_e03_core_mem_scope", "ix_evo_card_live", "ix_evo_card_scope",
    "ix_evo_case_scope", "ix_evo_trial_scope", "ix_persona_memories_scope",
    "ix_trait_history_scope", "ix_trait_observations_scope",
    "persona_custom_traits", "persona_memories", "persona_trait_history",
    "persona_trait_observations", "persona_trait_policy",
    "persona_trait_values", "tasks",
))
P02_OBJECTS = frozenset((
    "p02_chats", "p02_messages", "p02_attachments", "p02_gc",
    "p02_meta", "p02_messages_by_chat", "p02_messages_stable_seq",
))

def admit_shared_p02_store(original_store, principal: str) -> P02Store:
    """Reuse original Store.conn; backup before first additive P02 schema write.

    Original CoreID history and its model-weight identity gate are untouched.
    This is an ordinary global HELION chat; never remap Core chats to it.
    """
    if not isinstance(principal, str) or not principal or len(principal) > 128:
        raise PermissionError("E06_NATIVE_PRINCIPAL_REQUIRED")
    conn = getattr(original_store, "conn", None)
    path = getattr(original_store, "path", None)
    if not isinstance(conn, sqlite3.Connection) or path is None:
        raise RuntimeError("E06_ORIGINAL_STORE_CONNECTION_REQUIRED")
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("E06_ORIGINAL_SQLITE_PATH_HOLD")
    if conn.execute("PRAGMA user_version").fetchone() != (4,):
        raise RuntimeError("E06_ORIGINAL_V4_SCHEMA_REQUIRED")
    names = frozenset(str(row[0]) for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
    if not ORIGINAL_V4_OBJECTS.issubset(names):
        raise RuntimeError("E06_ORIGINAL_STORE_MISSING_OBJECTS")
    if names - ORIGINAL_V4_OBJECTS - P02_OBJECTS:
        raise RuntimeError("E06_ORIGINAL_STORE_UNRECOGNIZED_OBJECTS")
    if not names & P02_OBJECTS:
        snapshot = path.with_name(path.name + ".pre-p02-native.sqlite3")
        if snapshot.exists() or snapshot.is_symlink():
            raise RuntimeError("E06_P02_PRE_MIGRATION_BACKUP_EXISTS")
        # CreateNew: never clobber a previous user backup.
        fd = os.open(snapshot, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        backup = None
        try:
            backup = sqlite3.connect(str(snapshot))
            conn.backup(backup)
            if backup.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("E06_P02_PRE_MIGRATION_BACKUP_INVALID")
        except Exception:
            if backup is not None:
                backup.close()
            snapshot.unlink(missing_ok=True)
            raise
        else:
            backup.close()
    # One existing SQLite connection / file, original user_version 4 retained.
    store = P02Store(conn, path.parent / "p02-attachments",
                     approved_host_tables=ORIGINAL_V4_OBJECTS)
    store.initialize()
    if conn.execute("PRAGMA user_version").fetchone() != (4,):
        raise RuntimeError("E06_ORIGINAL_SCHEMA_VERSION_CHANGED")
    try:
        store.history("local", principal, "default", 1)
    except PermissionError:
        # If 'default' exists for another owner, create_chat will reject;
        # never adopt or overwrite their history.
        store.create_chat("local", principal, "default")
    return store


def serve_existing_store(original_store, run_id: str) -> int:
    if type(run_id) is not str or not 1 <= len(run_id) <= 128 or any(
            not 32 <= ord(c) <= 126 for c in run_id):
        raise ValueError("E06_NATIVE_RUNID_INVALID")
    principal = getpass.getuser().strip()
    if not principal or len(principal) > 128:
        raise PermissionError("E06_WINDOWS_USER_REQUIRED")
    p02 = admit_shared_p02_store(original_store, principal)
    catalog = {"version": "NOX-INTEGRATION-PACK-01",
               "actions": [{"taskId": f"NIP01-{i:02d}", "routeId": name,
                            "owner": owner, "risk": risk, "settings": []}
                           for i, (name, owner, risk)
                           in enumerate(APPROVED_NATIVE_POLICY, 1)]}
    dispatcher = NoxPackHost(catalog)
    routes = frozenset(("helion.chat", "chat.model", "chat.history",
                        "chat.stop", "models.installed"))
    session = NativeSession("local", principal, "default", allowed=routes,
                            private_approved=frozenset(("chat.history",)))
    evidence = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    # Existing P02 owner: localhost Ollama + one injected SQLite connection,
    # STOP and atomic history. No second provider/host/store.
    client = OllamaClient()
    ExistingP02Adapter(client, p02).register(dispatcher, receipt=evidence)

    def installed_models(_session, args):
        if type(args) is not dict or args:
            raise PermissionError("E06_MODEL_INVENTORY_REQUIRES_EMPTY_PAYLOAD")
        try:
            models = discover_installed_local_models()
        except (OSError, ConnectionError, TimeoutError):
            return {"models": [], "provider_state": "OFFLINE"}
        if isinstance(models, dict):
            models = models.get("models")
        if not isinstance(models, (list, tuple)):
            raise RuntimeError("E06_MODEL_INVENTORY_INVALID")
        names = []
        for model in models:
            name = model if isinstance(model, str) else (
                model.get("name") if isinstance(model, dict) else None)
            if not isinstance(name, str) or not 1 <= len(name) <= 256:
                raise RuntimeError("E06_MODEL_NAME_INVALID")
            if name in names:
                raise RuntimeError("E06_MODEL_DUPLICATE")
            names.append(name)
            if len(names) > 256:
                raise RuntimeError("E06_MODEL_INVENTORY_OVERSIZE")
        return {"models": names, "source": "ORIGINAL_LOCAL_DISCOVERY"}
    dispatcher.bind("models.installed", BoundPort(installed_models,
                    lambda: True, evidence, 3))
    ingress = NativeIngress(dispatcher, lambda: session,
                            expected_run_id=run_id, allow_modelcenter_reads=True)
    serve_native_frames(ingress, sys.stdin.buffer, sys.stdout.buffer)
    return 0
