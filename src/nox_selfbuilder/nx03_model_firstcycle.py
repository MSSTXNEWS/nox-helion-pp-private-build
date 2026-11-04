"""NX-03: native-only bridge from the existing P02 coder to the sandbox cycle.

The trusted OneHost owner, not the WebView or the model, must provide scope,
consent, epoch, a real native ACK and the isolated test runner. This is NOT
an installed Windows E07 or permission to modify the application.
"""
from __future__ import annotations
import ast
import json
import re
from typing import Callable
from .firstcycle_native import NativeFirstCycle, sha256
from .p02_coder import P02Coder

TARGET = "extensions/model_report/summary.py"
SCHEMA = "NOX-NX03-P02-SOURCE-v1"


class NX03Hold(RuntimeError):
    pass


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise NX03Hold("NX03_DUPLICATE_MODEL_FIELD")
        obj[key] = value
    return obj


def _constant(_value):
    raise NX03Hold("NX03_NONFINITE_MODEL_JSON")


def parse_model_source(raw):
    if type(raw) is not str or not 0 < len(raw.encode("utf-8")) <= 22000:
        raise NX03Hold("NX03_MODEL_OUTPUT_BOUNDS")
    try:
        doc = json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise NX03Hold("NX03_MODEL_NOT_STRICT_JSON") from exc
    if (type(doc) is not dict or set(doc) != {"schema", "relative_path", "source"}
            or doc["schema"] != SCHEMA or doc["relative_path"] != TARGET
            or type(doc["source"]) is not str):
        raise NX03Hold("NX03_MODEL_SOURCE_SCHEMA_HOLD")
    source = doc["source"].encode("utf-8")
    if not 0 < len(source) <= 16384:
        raise NX03Hold("NX03_MODEL_SOURCE_BOUNDS")
    try:
        tree = ast.parse(source.decode("utf-8"), filename=TARGET)
    except (SyntaxError, UnicodeError) as exc:
        raise NX03Hold("NX03_SOURCE_SYNTAX_HOLD") from exc
    if (len(tree.body) != 1 or type(tree.body[0]) is not ast.FunctionDef
            or tree.body[0].name != "summarize_status"
            or tree.body[0].decorator_list or len(tree.body[0].args.args) != 1
            or tree.body[0].args.args[0].arg != "items"
            or tree.body[0].args.posonlyargs or tree.body[0].args.kwonlyargs
            or tree.body[0].args.vararg or tree.body[0].args.kwarg
            or tree.body[0].args.defaults or tree.body[0].args.kw_defaults):
        raise NX03Hold("NX03_SOURCE_SHAPE_DENIED")
    forbidden = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
                 ast.ClassDef, ast.AsyncFunctionDef, ast.Lambda, ast.Await,
                 ast.Yield, ast.YieldFrom, ast.Delete)
    sensitive = {"eval", "exec", "compile", "open", "__import__", "getattr",
                 "setattr", "delattr", "globals", "locals", "vars", "input"}
    for node in ast.walk(tree):
        if isinstance(node, forbidden) or (isinstance(node, ast.Name)
                                              and node.id in sensitive):
            raise NX03Hold("NX03_SOURCE_CAPABILITY_DENIED")
    return source


def run_native_model_cycle(*, coder: P02Coder, native_session, session_token: str,
                           source_head: str, task_id: str, task: str, workspace,
                           preimage_sha256: str, current_head: Callable,
                           stop_epoch: Callable, stopped: Callable,
                           native_ack: Callable, authorize: Callable,
                           run_isolated_test: Callable) -> dict:
    """A single model-produced candidate, actual apply, and exact rollback.

    The owner may call this from an authenticated native callback only. Model
    JSON never supplies the trusted ACK, session, permissions, path or hashes.
    """
    if not isinstance(coder, P02Coder):
        raise NX03Hold("NX03_EXISTING_P02_CODER_REQUIRED")
    if (not isinstance(source_head, str)
            or not re.fullmatch(r"[0-9a-f]{40}", source_head)
            or not isinstance(preimage_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", preimage_sha256)
            or not isinstance(session_token, str) or not 0 < len(session_token) <= 128
            or not isinstance(task_id, str)
            or not re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]{2,79}", task_id)
            or not isinstance(task, str) or not 15 <= len(task) <= 3000
            or not all(callable(f) for f in (current_head, stop_epoch, stopped,
                                             native_ack, authorize, run_isolated_test))):
        raise NX03Hold("NX03_NATIVE_SCOPE_REQUIRED")
    validate = getattr(native_session, "validate", None)
    if not callable(validate) or validate() is False:
        raise NX03Hold("NX03_NATIVE_SESSION_REQUIRED")
    epoch = stop_epoch()
    if type(epoch) is not int or epoch < 0:
        raise NX03Hold("NX03_NATIVE_EPOCH_REQUIRED")

    def revoked():
        try:
            return (stopped() is not False or stop_epoch() != epoch
                    or current_head() != source_head)
        except Exception:
            return True

    if revoked():
        raise NX03Hold("NX03_STOP_OR_HEAD_DRIFT")
    model_json = coder(native_session, {
        "task": task, "source_head": source_head,
        "output_contract": {"schema": SCHEMA, "relative_path": TARGET,
                            "source": "Python source defining summarize_status(items)"},
        "native_write_authorized": False})
    if revoked():
        raise NX03Hold("NX03_REVOKED_AFTER_MODEL")
    candidate = parse_model_source(model_json)
    digest = sha256(candidate)
    scope = {"source_head": source_head, "task_id": task_id,
             "session": session_token, "path": TARGET,
             "candidate_sha256": digest, "preimage_sha256": preimage_sha256}
    ack = native_ack(dict(scope))  # Authentic native owner, not model output.
    if revoked() or type(ack) is not dict or ack.get("epoch") != epoch:
        raise NX03Hold("NX03_NATIVE_ACK_REVOKED_OR_WRONG_EPOCH")
    cycle = NativeFirstCycle(
        workspace=workspace, source_head=source_head, task_id=task_id,
        session=session_token, candidate=candidate,
        preimage_sha256=preimage_sha256, candidate_sha256=digest,
        native_ack=ack, authorize=authorize, stopped=revoked,
        run_isolated_test=run_isolated_test)
    if revoked():
        raise NX03Hold("NX03_REVOKED_BEFORE_TEST")
    cycle.test()
    cycle.apply()
    try:
        if revoked():
            raise NX03Hold("NX03_REVOKED_AFTER_APPLY")
    finally:
        try:
            cycle.rollback()  # Requires independent native rollback grant.
        except Exception as exc:
            raise NX03Hold("NX03_ROLLBACK_NOT_VERIFIED") from exc
    return {"schema": "NOX-NX03-NATIVE-FIRSTCYCLE-v1",
            "status": "MODEL_CANDIDATE_SANDBOX_ROLLBACK_VERIFIED",
            "origin": "EXISTING_P02_CODER", "source_head": source_head,
            "task_id": task_id, "preimage_sha256": preimage_sha256,
            "candidate_sha256": digest, "rollback_sha256": preimage_sha256,
            "installed_windows_e07": False, "selfbuild_ready": False,
            "release_accepted": False}
