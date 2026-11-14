#!/usr/bin/env python3
"""Import into existing NOX Resonance/chat_proxy handler. NO new HTTP backend.
Translate owner chat intents to strictly allowlisted control tasks. Side effects
happen only through a trusted server-side queue_writer callback.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import re
import uuid

ALLOW = {
    "gpu": ("gpu", False),
    "disk": ("disk", False),
    "processes": ("processes", False),
    "checkpoint": ("checkpoint", False),
    "training_status": ("training_status", False),
    "prepare": ("prepare_local", True),
    "stage": ("stage_fast75", True),
    "resume": ("arm_resume_training", True),
    "cancel_auto": ("cancel_auto_resume", True),
}
WORDING = (
    (r"(?:\bgpu\b|\ba100\b|видеокарт|температур|загрузк[ауи] gpu)", "gpu"),
    (r"(?:\bдиск\b|свободн.*мест|хранилищ)", "disk"),
    (r"(?:\bпроцесс\b|диспетчер|watchdog)", "processes"),
    (r"(?:checkpoint|чекпоинт|контрольн.{0,12}точк|последн.{0,10}шаг)", "checkpoint"),
    (r"(?:статус.{0,14}обучени|прогресс.{0,14}обучени|токен.{0,4}секунд)", "training_status"),
    (r"(?:подготов.{0,15}локальн|найди.{0,15}данн.{0,5}обучени)", "prepare"),
    (r"(?:установ.{0,15}fast75|подгруз.{0,15}fast75)", "stage"),
    (r"(?:запусти.{0,20}обучени|возобнов.{0,20}обучени|resume training|start training)", "resume"),
    (r"(?:отмени.{0,12}автозапуск|не запускать автоматически)", "cancel_auto"),
)

@dataclass(frozen=True)
class Auth:
    authenticated: bool
    owner: bool
    # Must be from existing login session, never from prompt/model-generated text.
    session_id: str

def parse_intent(text):
    if not isinstance(text, str) or len(text)>500:
        return None
    s=text.lower()
    # Safety overrides: no blind stop, process kill, deletion, disk wipe or root shell.
    if re.search(r"killall|pkill|rm -rf|sudo|root shell|удали.{0,25}(?:вес|чекпоинт|checkpoint)|убей.{0,20}процесс",s):
        return {"state":"HOLD_UNSUPPORTED_DANGEROUS_COMMAND"}
    for pattern,intent in WORDING:
        if re.search(pattern,s,re.I):
            return {"intent":intent}
    return None

def dispatch(text, auth, approved_intent=None, queue_writer=None):
    """queue_writer(task: dict) is a trusted backend callback returning acknowledgement.
    Never pass a GitHub token or callbacks from browser JS or from model output.
    """
    if not isinstance(auth,Auth) or not auth.authenticated or not auth.owner or not auth.session_id:
        return {"state":"HOLD_UNAUTHORIZED"}
    intent=parse_intent(text)
    if intent is None:
        return {"state":"NOT_A_CONTROL_COMMAND"}
    if "state" in intent: return intent
    name=intent["intent"]
    if name not in ALLOW:return {"state":"HOLD_UNKNOWN_ACTION"}
    op,mutation=ALLOW[name]
    if mutation and approved_intent!=name:
        return {"state":"CONFIRM_REQUIRED","action":name,
                "message":"Подтверди именно это действие отдельной кнопкой. Текст модели не считается подтверждением."}
    if queue_writer is None:
        return {"state":"HOLD_QUEUE_WRITER_UNAVAILABLE","action":name}
    ident="nox-"+uuid.uuid4().hex[:22]
    expiry=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat().replace("+00:00","Z")
    task={"id":ident,"op":op,"expires_utc":expiry}
    # queue_writer performs GitHub API write under the existing backend identity,
    # validates repository+branch+SHA and logs owner approval separately.
    try:
        response=queue_writer(task)
    except Exception:
        return {"state":"HOLD_QUEUE_REJECTED"}
    return {"state":"ENQUEUED_NOT_EXECUTED","action":name,
            "task_id":ident,"transport_receipt":bool(response)}
