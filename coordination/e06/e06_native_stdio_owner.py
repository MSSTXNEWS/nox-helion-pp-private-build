"""E06 source overlay for the ORIGINAL helion.app process.

Uses the one legacy Store, original localhost model inventory and existing
PACK01/NativeIngress framed protocol. No second DB, HTTP host, LLM or UI.
Production native WPF activation remains separately gated by Windows E2E.
"""
from __future__ import annotations
import getpass
import hashlib
import json
import sys
import stat
import threading
from dataclasses import fields, replace
from pathlib import Path

from nox_native_bridge import NoxPackHost, NativeSession, BoundPort, APPROVED_NATIVE_POLICY
from p02_native_ingress import NativeIngress
from p02_framed_worker import serve_native_frames
from p02_onehost import create_onehost_p02
from nox_selfbuilder.original_store_adapter import OriginalStoreChatAdapter

CHAT_ROUTES = frozenset({"helion.chat", "chat.history", "chat.stop", "chat.model"})


def _plain_path(value, *, directory=True):
    if type(value) is not str or not value or not Path(value).is_absolute():
        raise ValueError("E06_NATIVE_ABSOLUTE_PATH_REQUIRED")
    path = Path(value)
    for node in (path, *path.parents):
        try:
            reparse = getattr(node.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        except FileNotFoundError:
            reparse = 0
        if reparse or node.is_symlink() or getattr(node, "is_junction", lambda: False)():
            raise ValueError("E06_NATIVE_CONFIG_REPARSE_HOLD")
    if directory and not path.is_dir():
        raise ValueError("E06_NATIVE_DIRECTORY_REQUIRED")
    return path.resolve(strict=directory)


def load_native_config(data_dir):
    """Read owner-local configuration. It contains paths/job data, NEVER grants."""
    if data_dir is None:
        return {}
    root = _plain_path(str(data_dir))
    file = root / "onehost-native-config.json"
    if not file.exists():
        return {}
    _plain_path(str(file), directory=False)
    info = file.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
        raise ValueError("E06_NATIVE_CONFIG_FORMAT_HOLD")
    from p02_native_ingress import _reject_duplicate_fields, _reject_nonfinite, _finite_json_number
    config = json.loads(file.read_text("utf-8"), object_pairs_hook=_reject_duplicate_fields,
                        parse_constant=_reject_nonfinite, parse_float=_finite_json_number)
    if (type(config) is not dict or config.get("version") != 1 or
            set(config) - {"version", "source_root", "source_paths", "candidate_workspace", "forge_root", "forge_jobs",
                           "forge_python_exe", "forge_python_sha256"}):
        raise ValueError("E06_NATIVE_CONFIG_FIELDS_HOLD")
    for key in ("source_root", "candidate_workspace", "forge_root"):
        if key in config:
            config[key] = _plain_path(config[key])
    if "forge_python_exe" in config or "forge_python_sha256" in config:
        interpreter = _plain_path(config.get("forge_python_exe"), directory=False)
        expected = config.get("forge_python_sha256")
        if (not interpreter.is_file() or type(expected) is not str or len(expected) != 64 or
                any(c not in "0123456789abcdef" for c in expected) or
                hashlib.sha256(interpreter.read_bytes()).hexdigest() != expected):
            raise ValueError("E06_APPROVED_P04_INTERPRETER_SHA_HOLD")
        config["forge_python_exe"] = interpreter
    if "source_root" in config:
        from nox_selfbuilder.onehost_builder import ManagedSource
        managed = ManagedSource(config["source_root"])
        if not managed.admitted(managed.head()):
            raise ValueError("E06_NATIVE_SOURCE_DIRTY_HOLD")
    if ("source_root" in config and "candidate_workspace" in config and
            config["candidate_workspace"].is_relative_to(config["source_root"])):
        raise ValueError("E06_CANDIDATES_MUST_NOT_OVERWRITE_SOURCE")
    source_paths = config.get("source_paths", [])
    if (type(source_paths) is not list or len(source_paths) > 30 or
            any(type(path) is not str or not path or Path(path).is_absolute() or
                "\\" in path or any(part in {"", ".", ".."} for part in path.split("/"))
                for path in source_paths)):
        raise ValueError("E06_NATIVE_SOURCE_PATHS_HOLD")
    raw_jobs = config.get("forge_jobs", [])
    if type(raw_jobs) is not list or len(raw_jobs) > 32:
        raise ValueError("E06_NATIVE_JOB_REGISTRY_HOLD")
    from nox_selfbuilder.background_forge import ForgeJob
    allowed = {field.name for field in fields(ForgeJob)}
    path_keys = {"base_model_dir", "model_lock", "dataset_manifest", "rights_verifier",
                 "train_jsonl", "holdout_jsonl", "output_dir"}
    jobs = {}
    for row in raw_jobs:
        if type(row) is not dict or set(row) - allowed:
            raise ValueError("E06_NATIVE_JOB_FIELDS_HOLD")
        item = dict(row)
        for key in path_keys:
            item[key] = _plain_path(item[key], directory=key == "base_model_dir")
        job = ForgeJob(**item)
        if job.run_id in jobs:
            raise ValueError("E06_NATIVE_JOB_DUPLICATE")
        jobs[job.run_id] = job
    config["forge_jobs"] = jobs
    return config


def create_existing_ingress(store, run_id: str, *, client=None, event_sink=None,
                            owner_ports=(), native_approve=None, data_dir=None):
    """Bind approved P02 methods to the original host and original Store actor.

    The actor is created by the original CLI on its connection-owning thread.
    No connection crosses the frame-worker thread and no P02 SQLite is created.
    The caller is the authenticated private native pipe, never page JSON.
    """
    if (getattr(store, "is_original_store_actor", False) is not True or
            not callable(getattr(store, "call", None))):
        raise RuntimeError("E06_ORIGINAL_STORE_ACTOR_REQUIRED")
    if type(run_id) is not str or not 1 <= len(run_id) <= 128 or any(
            not 32 <= ord(c) <= 126 for c in run_id):
        raise ValueError("E06_NATIVE_RUNID_INVALID")
    principal = getpass.getuser().strip()
    if not principal or len(principal) > 128:
        raise PermissionError("E06_WINDOWS_USER_REQUIRED")
    # Canonical route/owner/risk table from the approved existing PACK01 code,
    # never a browser-supplied catalogue or an alternate native dispatcher.
    catalog = {"version": "NOX-INTEGRATION-PACK-01",
               "actions": [{"taskId": f"NIP01-{i:02d}", "routeId": name,
                            "owner": owner, "risk": risk, "settings": []}
                           for i, (name, owner, risk)
                           in enumerate(APPROVED_NATIVE_POLICY, 1)]}
    dispatcher = NoxPackHost(catalog, native_approve=native_approve)
    # Sensitive history is still independently consent-gated for EVERY request
    # by the existing Windows SID/origin/ACL bridge before it reaches this pipe.
    evidence = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    seed_archive = Path(__file__).resolve().parents[1] / "assets" / (
        "NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip")
    memory = OriginalStoreChatAdapter(store, seed_archive=seed_archive)
    adapter = create_onehost_p02(memory, client=client, event_sink=event_sink)
    config_hold = None
    try:
        config = load_native_config(data_dir)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        # Invalid optional code/training configuration cannot destroy the
        # original offline memory/chat backbone or silently grant privileges.
        config = {}
        config_hold = "E06_NATIVE_CONFIG_INVALID"
    from nox_selfbuilder.onehost_queue import NativeWorkQueue
    from nox_selfbuilder.onehost_builder import OneHostSelfBuilder
    lease_lock = threading.Lock()
    leases = {}

    def authorize(session, action, args):
        session.validate()
        if session.tenant != "local" or session.principal != principal:
            return False
        with lease_lock:
            return leases.get((session.chat_id, action)) == adapter._stop_epoch

    def grant(session, action, args):
        # Only entered after private-pipe native consent, not from a page flag.
        if not callable(native_approve) or native_approve(session, action, args) is not True:
            raise PermissionError("E06_FRESH_NATIVE_ACTION_CONSENT_REQUIRED")
        if action in {"selfbuilder.propose", "selfbuilder.worker.start", "training.start", "training.resume", "training.merge"} and queue.is_busy():
            raise RuntimeError("E06_NATIVE_WORKER_BUSY")
        if action in {"selfbuilder.propose", "selfbuilder.worker.start", "training.start", "training.resume", "training.merge"}:
            adapter.stop_event.clear()  # Fresh consent only; the revocation epoch NEVER resets.
        actions = {action}
        if action in {"selfbuilder.propose", "selfbuilder.worker.start"}:
            actions |= {"selfbuilder.propose", "selfbuilder.coding.generate", "selfbuilder.reflect",
                        "selfbuilder.proposal.persist"}
        with lease_lock:
            for permitted in actions:
                leases[(session.chat_id, permitted)] = adapter._stop_epoch

    queue = NativeWorkQueue(store, authorize=authorize, stop_requested=adapter.stop_requested,
                           stop_epoch=lambda: adapter._stop_epoch)
    def memory_scope(session):
        from helion.personas import PERSONAS, persona_chat_id
        project, core, chat = memory._scope(session.tenant, session.principal, session.chat_id)
        persona = next((p.persona_id for p in PERSONAS if persona_chat_id(p.persona_id) == chat), None)
        if persona is None:
            raise PermissionError("E06_SELECT_NATIVE_PERSONA_FOR_SOURCE_MEMORY")
        return {"project_id": project, "core_id": core, "persona_id": persona}
    builder = OneHostSelfBuilder(queue=queue, coder=adapter.create_coder(authorize),
        memory_scope=memory_scope, authorize=authorize, stop_requested=adapter.stop_requested,
        source_root=config.get("source_root"), workspace=config.get("candidate_workspace"),
        seed_archive=seed_archive, model_inventory=adapter.client.models,
        source_paths=config.get("source_paths", ()), stop_epoch=lambda: adapter._stop_epoch,
        request_stop=lambda session: stop(session, {}))
    forge_commands = None
    background = None
    forge_hold = ("GPU_TRAINING_HOLD_APPROVED_PYTHON_INTERPRETER_REQUIRED"
                  if config.get("forge_root") is not None and getattr(sys,"frozen",False) and
                  "forge_python_exe" not in config else None)
    training_lease = [None]
    def command(session, args):
        session, args = select_scope(session, args)
        action = args.get("action")
        if type(action) is str and action.startswith("training."):
            if forge_commands is None:
                raise RuntimeError("E06_APPROVED_NATIVE_FORGE_CONFIG_REQUIRED")
            if action in {"training.merge", "training.activate", "training.rollback"}:
                grant(session, action, args)
                if action == "training.merge":
                    training_lease[0] = (session.chat_id, action, adapter._stop_epoch)
            elif action == "training.import.prepare":
                grant(session, "training.import", args)
            return forge_commands(session, args)
        if action in {"selfbuilder.propose", "selfbuilder.worker.start", "selfbuilder.worker.stop", "selfbuilder.feedback"}:
            grant(session, action, args)
        result = builder.command(session, args)
        if action in {"selfbuilder.capabilities", "selfbuilder.worker.status"}:
            existing = {row.get("payload", {}).get("run_id"): row.get("state", "HOLD")
                        for row in queue.list(session) if row.get("kind") == "FORGE"}
            result = {**result, "trainingJobs": [{"id": key,
                "status": existing.get(key, "CONFIGURED_NOT_RUN")}
                for key in config.get("forge_jobs", {})]}
            if forge_hold:
                result["training_configuration_hold"] = forge_hold
            if action == "selfbuilder.capabilities":
                actions = dict(result.get("actions", {}))
                for key in ("training.merge", "training.import", "training.activate", "training.rollback", "selfbuilder.train.request"):
                    available = forge_commands is not None and bool(config.get("forge_jobs"))
                    actions[key] = {"available": available,
                        "status": "NATIVE_REQUEST_AVAILABLE" if available else "NATIVE_FORGE_CONFIG_HOLD",
                        "ownerConsent": True}
                result["actions"] = actions
        if action in {"selfbuilder.capabilities", "selfbuilder.worker.status"} and config_hold:
            result = {**result, "configuration_state": "HOLD", "configuration_reason": config_hold}
        return result
    def select_scope(session, args):
        args = dict(args)
        if "core_id" in args or "persona_id" in args:
            chat_id = memory.resolve_chat_id(args.pop("core_id", None), args.pop("persona_id", None))
            session = replace(session, chat_id=chat_id)
        return session, args
    dispatcher.bind("chat.commands", BoundPort(command, lambda: True, evidence, 2))
    stop_hooks = []
    def stop(session, args):
        result = adapter.stop(session, args)
        for hook in stop_hooks:
            hook()
        return result
    for route, method in (("helion.chat", adapter.chat),
                          ("chat.history", adapter.history),
                          ("chat.stop", stop),
                          ("chat.model", adapter.list_models)):
        # History and STOP remain usable with no large model installed. Chat's
        # own provider validates a real selected model and fails closed.
        dispatcher.bind(route, BoundPort(method, lambda: True, evidence, 2))
    # Reuse P03's existing read adapter and this exact Ollama client.
    from p03_onehost_port import P03OneHostPort
    p03 = P03OneHostPort(adapter.client)
    p03.register(dispatcher, BoundPort, receipt=evidence)
    if config.get("forge_root") is not None and forge_hold is None:
        from nox_selfbuilder.background_forge import ExistingP04Background
        from nox_selfbuilder.p04_forge_bridge import ExistingP04NativePorts, ExistingP04Pipeline
        p04_dir = Path(__file__).resolve().parents[1] / "Packages" / "P04"
        def training_permitted():
            with lease_lock:
                lease = training_lease[0]
                return (lease is not None and lease[2] == adapter._stop_epoch and
                        leases.get((lease[0], lease[1])) == lease[2])
        background = ExistingP04Background(trusted_root=config["forge_root"], p04_dir=p04_dir,
            owner_permit=training_permitted,
            owner_stop=adapter.stop_requested, owner_busy=lambda: True,
            python_exe=config.get("forge_python_exe"))
        stop_hooks.append(background.request_stop)
        def resolve_job(session, job_id):
            session.validate()
            job = config.get("forge_jobs", {}).get(job_id)
            if job is None:
                raise RuntimeError("E06_APPROVED_NATIVE_FORGE_JOB_REQUIRED")
            return job
        def submit_job(session, job, callback):
            return queue.submit(session, job, callback)
        def last_run(session, job):
            queue.register_forge(session, job)
            return queue.last_run(session, job)
        ports = ExistingP04NativePorts(background, job_resolver=resolve_job,
            last_run=last_run, native_submit=submit_job)
        def installed_digest(session, tag):
            value = p03.digest(session, {"modelTag": tag}).get("ollamaReportedManifestDigest")
            if not isinstance(value, str) or not value.startswith("sha256:"):
                raise RuntimeError("E06_ACTUAL_INSTALLED_MODEL_DIGEST_REQUIRED")
            return value[7:]
        pipeline = ExistingP04Pipeline(background, queue, adapter, job_resolver=resolve_job,
            authorize=authorize, model_digest=installed_digest,
            receipt_root=Path(data_dir) / "receipts")
        forge_commands = pipeline.command
        for route, method in ports.METHODS.items():
            original = getattr(ports, method)
            def invoke(session, args, route=route, original=original):
                session, args = select_scope(session, args)
                if route in {"training.start", "training.resume"}:
                    grant(session, route, args)
                    training_lease[0] = (session.chat_id, route, adapter._stop_epoch)
                return original(session, args)
            dispatcher.bind(route, BoundPort(invoke, lambda: True, evidence, 4))
    # Only concrete native-owned, receipt-bound methods may extend the scope.
    # bind() rejects duplicate routes and mismatched immutable policy owners.
    for route, port in owner_ports:
        dispatcher.bind(route, port)
    allowed = frozenset(dispatcher.ports)
    private = frozenset(route for route in allowed
                        if dispatcher.routes[route]["risk"] != "safe")
    scope = NativeSession("local", principal, "default", allowed=allowed,
                          private_approved=private)
    ingress = NativeIngress(dispatcher, lambda: scope,
                            expected_run_id=run_id, allow_modelcenter_reads=True,
                            allow_owner_routes=frozenset(route for route in allowed
                                if dispatcher.routes[route]["owner"] == 4))
    # The existing framed pump installs its atomic same-request event writer.
    # This forwards real Ollama deltas; it is not a second event transport.
    ingress.bind_event_sink = lambda sink: setattr(adapter, "event_sink", sink)
    ingress.p02 = adapter  # Same client for the existing SELF-BUILDER; not a second runtime.
    ingress.forge = background
    ingress.configuration_hold = config_hold
    ingress.close = queue.close
    return ingress


def serve_existing_store(store, run_id: str, data_dir=None) -> int:
    # This entry is invoked only by the original WPF private pipe. Its native
    # SID/origin/ACL bridge already obtained fresh per-action consent BEFORE
    # sending a frame; no page-supplied consent field is accepted by ingress.
    principal = getpass.getuser().strip()
    def private_pipe_approval(session, route, args):
        session.validate()
        return session.tenant == "local" and session.principal == principal
    ingress = create_existing_ingress(store, run_id, data_dir=data_dir,
                                       native_approve=private_pipe_approval)
    # stdout must contain ONLY authenticated binary P02 frames.
    try:
        serve_native_frames(ingress, sys.stdin.buffer, sys.stdout.buffer)
    finally:
        ingress.p02.stop(None, {})
        ingress.close()
    return 0
