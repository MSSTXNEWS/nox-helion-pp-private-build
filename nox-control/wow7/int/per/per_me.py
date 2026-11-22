"""PER-12: панель «Кто я» и откат характера. me_payload() - данные для UI; rollback_me() - только с подписью мессира;
make_router() - FastAPI-роутер GET /me, POST /me/rollback (Bearer NOX_OWNER_TOKEN; без токена в окружении роутер отказывает всем)."""
import hmac
import os

import perpath  # noqa: F401
from personality import AXES, AXIS_RU
from development import PHASE_RU

SIGN_PHRASE = "подписано мессиром"


def me_payload(pers, dev, beliefs, now=None):
    chk = dev.check(now)
    return {"axes": {a: {"name": AXIS_RU[a], "value": round(pers.axes[a], 3)} for a in AXES},
            "temperament": {k: round(v, 3) for k, v in pers.temperament.items()},
            "signature": pers.signature()[0], "phase": PHASE_RU[dev.phase], "next": chk["next"], "missing": chk["missing"],
            "milestones": {k: v["detail"] for k, v in dev.s["milestones"].items()},
            "why_changed": pers.why_changed(n=8),
            "beliefs": [{"id": b["id"], "text": b["text"], "status": b["status"], "percent": round(b["conf"] * 100)}
                        for b in beliefs.items.values() if b["status"] in ("accepted", "contested")],
            "snapshots": sorted(pers.snapshots, key=lambda k: pers.snapshots[k]["ts"])}


def rollback_me(pers, label, signature, traits=None):
    """Если передан traits (TRAITS.Traits) - откат ОДНОЙ командой для TRAITS+PER (TRAITS/persona_rollback); иначе только оси PER."""
    if signature != SIGN_PHRASE:
        return {"ok": False, "error": "нужна подпись мессира"}
    if label not in pers.snapshots or (traits is not None and label not in traits.snapshots):
        return {"ok": False, "error": "нет снапшота %r" % label}
    if traits is not None:
        import persona_rollback
        persona_rollback.rollback_all(traits, pers, label, "откат из панели «Кто я»")
    else:
        pers.rollback(label, "откат из панели «Кто я»")
    return {"ok": True, "label": label, "axes": {a: round(pers.axes[a], 3) for a in AXES}}


def make_router(state_dir=None):
    from fastapi import APIRouter, Header, HTTPException
    from beliefs import Beliefs
    from development import Development
    from personality import Personality
    d = state_dir or os.environ.get("NOX_STATE", "/root/nox/state")
    r = APIRouter()

    def auth(h):
        tok = os.environ.get("NOX_OWNER_TOKEN", "")
        if not tok or not hmac.compare_digest((h or "").removeprefix("Bearer ").encode("utf-8"), tok.encode("utf-8")):
            raise HTTPException(403, "только владелец")

    def load():
        j = lambda n: os.path.join(d, n)
        return Personality(path=j("personality.json")), Development(path=j("development.json")), Beliefs(path=j("beliefs.json"))

    @r.get("/me")
    def me(authorization: str = Header(None)):
        auth(authorization)
        return me_payload(*load())

    @r.post("/me/rollback")
    def rb(body: dict, authorization: str = Header(None)):
        auth(authorization)
        tp = os.path.join(d, "traits.json")
        tr = None
        if os.path.exists(tp):
            import traits as T
            tr = T.Traits(path=tp)
        return rollback_me(load()[0], body.get("label"), body.get("signature"), tr)
    return r
