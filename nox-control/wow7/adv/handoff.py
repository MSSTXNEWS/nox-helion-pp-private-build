"""handoff: ручная передача вопроса официальному веб-чату (без API, без автоматизации) и приём вставленного ответа как НЕПРОВЕРЕННОГО.
Основа: NOX_ONLINE_ADVISORS_CORE_20261117 (nox_advisors/handoff.py + models.py), переписано без зависимостей от пакета.
Сайт не открывается, вход/CAPTCHA не обходятся; платные сервисы Создатель использует сам и на своих условиях (канон Q21: NOX их не вызывает)."""
import hashlib
import re

SECRET = re.compile(r'(?:\bBearer\s+[A-Za-z0-9_.-]{12,}|\bsk-(?:or-v1-)?[A-Za-z0-9_-]{12,}|(?:api[_-]?key|password|secret)\s*[:=]\s*["\']?[A-Za-z0-9_./+-]{12,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)', re.I)
BULK_MEMORY = re.compile(r'(?:"s03_items"\s*:\s*\[|S03_FULL_DUMP|BEGIN_S03_DUMP|\bINSERT\s+INTO\s+s03_items\b)', re.I)
WEB_UI = {"chatgpt": "https://chatgpt.com/", "gemini": "https://gemini.google.com/", "claude": "https://claude.ai/"}
TRUST = {"authority": "UNTRUSTED_ADVICE_NO_TOOL_AUTHORITY", "factual_claims_verified": False, "cited_urls_verified": False, "requires_host_verification": True}


def sensitive(text):
    return bool(SECRET.search(text or "") or BULK_MEMORY.search(text or ""))


def human_web_handoff(service, brief, request_id):
    if service not in WEB_UI:
        raise ValueError("WEB_SERVICE_NOT_ALLOWED")
    if not isinstance(brief, str) or not 1 <= len(brief.strip()) <= 6000:
        raise ValueError("BOUNDED_BRIEF_REQUIRED")
    if sensitive(brief):
        raise ValueError("SENSITIVE_OR_BULK_CONTEXT_REJECTED")
    return {"status": "WAITING_FOR_HUMAN", "service": service, "url": WEB_UI[service], "request_id": request_id, "brief": brief,
            "brief_sha256": hashlib.sha256(brief.encode()).hexdigest(), "automatic_submission": False,
            "instructions": "Откройте сервис сами, проверьте его условия/квоту, отправьте только этот текст и вставьте ответ командой «ответ советника <id>: …»."}


def receive_human_reply(handoff, text, reported_model=None):
    if not isinstance(text, str) or not text.strip() or len(text) > 32000:
        raise ValueError("BOUNDED_REPLY_REQUIRED")
    if SECRET.search(text):
        raise ValueError("SENSITIVE_REPLY_REJECTED")
    return dict(TRUST, request_id=handoff["request_id"], advisor=handoff["service"], model=reported_model or "USER_REPORTED_UNSPECIFIED",
                text=text, evidence_kind="human_pasted_unverified_model_advice", source=handoff["url"], brief_sha256=handoff["brief_sha256"])
