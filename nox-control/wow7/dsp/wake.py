"""DSP wake: БУДИТЬ NOX после холодного старта/рестарта GLM: событие «пробуждение» в я-модель и шину, прогрев KV души, утренний отчёт.
Ничего не выдумывает: отчёт строится из журнала диспетчера. Тихие часы: отчёт и «заговаривание» только после 08:00 МСК (файл/шина, не голос)."""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import glob
import importlib.util
import json
import os
import sys
import time
from datetime import datetime

import nox_dispatcher as nd


def _load_self_model(d):
    for p in (os.path.join(d.home, "src/con/nox_self_model_live.py"), os.path.join(d.reg.ctl, "wow7/con/nox_self_model_live.py")):
        if os.path.isfile(p):
            spec = importlib.util.spec_from_file_location("nox_self_model_live_dsp", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.LiveSelfModel(path=os.path.join(d.home, "state/self_live.json"))
    return None


def _bus(d):
    sys.path.insert(0, d.reg.ctl)
    try:
        from qs6.events_bus import EventBus
        return EventBus(os.environ.get("NOX_EVENTS") or os.path.join(d.home, "memory/events.jsonl"))
    except Exception:  # noqa: BLE001
        return None
    finally:
        if d.reg.ctl in sys.path:
            sys.path.remove(d.reg.ctl)


def owner_recently_active(d, within_s=120):
    last = nd.load_json(os.path.join(d.home, "state/self_live.json"), {}).get("last_owner_ts")
    return bool(last) and d.now() - last < within_s


def warm_kv(d):
    """Прогрев KV души. Предпочтительно SPD-04 soul_kv_warm.sh (restore/save слота по ключу); иначе один токен с cache_prompt."""
    if owner_recently_active(d):
        return {"ok": False, "deferred": True, "text": "мессир сейчас пишет: прогрев отложен"}
    for script in (os.path.join(d.home, "scripts/soul_kv_warm.sh"), os.path.join(d.reg.ctl, "wow7/spd/soul_kv_warm.sh")):
        if os.path.isfile(script):
            import subprocess
            r = subprocess.run(["bash", script, "--port", str(d.reg.services["glm"]["port"]), "auto"], capture_output=True, text=True, timeout=1800)
            return {"ok": r.returncode == 0, "text": "soul_kv_warm.sh auto rc=%d %s" % (r.returncode, (r.stdout + r.stderr).strip()[-160:])}
    soul = os.path.join(d.home, "state/soul_prompt_ru.txt")
    if not os.path.isfile(soul):
        return {"ok": False, "text": "нет файла души %s - нечего греть" % soul}
    code, body = nd.http("POST", "http://127.0.0.1:%d/v1/chat/completions" % d.reg.services["glm"]["port"],
                         {"messages": [{"role": "system", "content": open(soul, encoding="utf-8").read()}, {"role": "user", "content": "Проверка связи."}],
                          "max_tokens": 1, "temperature": 0, "cache_prompt": True, "id_slot": 0}, timeout=1800)
    return {"ok": code == 200, "text": "прогрев душой через chat: HTTP %s" % code}


def wake_now(d, force=False, reason="manual"):
    """Событие «пробуждение»: я-модель wake() + шина. Возвращает словарь с тем, что реально получилось."""
    out = {"reason": reason, "ts": d.now()}
    try:
        m = _load_self_model(d)
        out["self_model"] = m.wake() if m else "я-модель не найдена (CON-04 не установлен)"
    except Exception as e:  # noqa: BLE001
        out["self_model"] = "ошибка: %s: %s" % (type(e).__name__, e)
    bus = _bus(d)
    if bus:
        try:
            ev = bus.publish("nox.wake", {"reason": reason, "services": {n: v.get("state") for n, v in d.last_status.items()}, "dsp": nd.VERSION}, source="dsp")
            out["bus"] = ev.get("seq") if isinstance(ev, dict) else "published"
        except Exception as e:  # noqa: BLE001
            out["bus"] = "ошибка: %s" % e
    else:
        out["bus"] = "шина qs6.events_bus недоступна"
    d.ev("wake", None, "пробуждение (%s): я-модель=%s шина=%s" % (reason, json.dumps(out["self_model"], ensure_ascii=False)[:80], out["bus"]))
    if not d.dry:
        nd.atomic_write(os.path.join(d.home, "state/dsp_wake.json"), json.dumps(out, ensure_ascii=False, default=str))
    return out


def boot_marker(d):
    return os.environ.get("DSP_BOOT_MARKER") or "/dev/shm/.nox_dsp_boot"


def step(d, statuses):
    w = d.st["wake"]
    now = d.now()
    up = lambda n: statuses.get(n, {}).get("state") == "UP"  # noqa: E731
    # 1. определить, что NOX «спал»
    if not w.get("pending"):
        reason = None
        if not os.path.exists(boot_marker(d)):
            reason = "холодный старт контейнера (tmpfs очищен)"
            if not d.dry:
                open(boot_marker(d), "w").write(str(now))
        elif d.st.get("last_tick") and now - d.st["last_tick"] > 600:
            reason = "диспетчер молчал %d мин" % ((now - d.st["last_tick"]) // 60)
        glm_pid = (statuses.get("glm", {}).get("pids") or [None])[0]
        if reason is None and "glm" in statuses and up("glm") and glm_pid != d.st.get("glm_pid") and d.st.get("glm_pid") is not None:
            reason = "GLM перезапущен (KV души потерян)"
        if reason:
            d.st["wake"] = w = {"pending": True, "reason": reason, "since": now, "event": False, "kv": not ("glm" in statuses), "report": False}
            d.ev("wake_pending", None, reason)
    if "glm" in statuses and up("glm"):
        d.st["glm_pid"] = (statuses["glm"].get("pids") or [None])[0]
    d.st["last_tick"] = now
    if not w.get("pending"):
        daily_report(d)
        return
    # 2. шаги
    if not w["event"] and up("fast") and (up("gateway") or "gateway" not in statuses):
        wake_now(d, reason=w["reason"])
        w["event"] = True
    if not w["kv"] and up("glm"):
        r = warm_kv(d)
        d.ev("kv_warm", "glm", r["text"], ok=r["ok"])
        if r["ok"] or not r.get("deferred"):
            w["kv"] = True
            w["kv_ok"] = r["ok"]
    if w["event"] and w["kv"]:
        w["pending"] = False
        w["done_ts"] = now
        d.ev("wake_done", None, "пробуждение завершено за %d с (KV прогрет: %s)" % (now - w["since"], w.get("kv_ok")))
    elif now - w["since"] > 7200:
        w["pending"] = False
        d.ev("wake_timeout", None, "пробуждение не завершилось за 2 ч: GLM так и не стал здоров")
    daily_report(d)


def morning_report(d, force=False):
    now = d.now()
    since = now - 86400
    evs = [e for e in d.st["events"] if e["ts"] >= since]
    cnt = {}
    for e in evs:
        cnt[e["kind"]] = cnt.get(e["kind"], 0) + 1
    lines = ["# Утренний отчёт диспетчера, %s МСК" % datetime.fromtimestamp(now, nd.MSK).strftime("%d.%m.%Y %H:%M"),
             "", "Версия DSP: %s. За сутки: пробуждений %d, запусков %d, отказов %d, плейбуков %d, обновлений %d." % (
                 nd.VERSION, cnt.get("wake", 0), cnt.get("start", 0), cnt.get("fail", 0), cnt.get("playbook", 0), cnt.get("update", 0)), ""]
    lines.append("Сейчас: " + ", ".join("%s=%s" % (n, v.get("state")) for n, v in d.last_status.items()))
    lines.append("Диск свободно: %.1f ГБ, память доступна: %.0f ГБ." % (d.sys.disk_free_gb(), d.sys.mem_available_gb()))
    bad = [e for e in evs if e["kind"] in ("fail", "playbook", "quarantine", "hung", "watchdog_revive", "update_error")]
    if bad:
        lines += ["", "Что происходило (последние 15):"]
        for e in bad[-15:]:
            lines.append("- %s %s [%s] %s" % (datetime.fromtimestamp(e["ts"], nd.MSK).strftime("%H:%M"), e.get("svc") or "-", e["kind"], e["text"]))
    else:
        lines += ["", "Ночь прошла без отказов и починок."]
    try:
        m = _load_self_model(d)
        if m:
            lines += ["", "Автобиография (я-модель):"] + ["- " + x for x in m.autobiography(3, kinds=("birth", "wake"))]
    except Exception:  # noqa: BLE001
        pass
    text = "\n".join(lines)
    day = datetime.fromtimestamp(now, nd.MSK).strftime("%Y%m%d")
    if not d.dry:
        nd.atomic_write(os.path.join(d.home, "state/dsp_morning_%s.md" % day), text)
        bus = _bus(d)
        if bus:
            try:
                bus.publish("nox.morning_report", {"day": day, "file": "state/dsp_morning_%s.md" % day, "failures": cnt.get("fail", 0)}, source="dsp")
            except Exception:  # noqa: BLE001
                pass
    d.st["report_day"] = day
    d.ev("morning_report", None, "отчёт за %s записан" % day)
    return text


def daily_report(d):
    day = datetime.fromtimestamp(d.now(), nd.MSK).strftime("%Y%m%d")
    h = d.msk_hour()
    if d.st.get("report_day") != day and not d.in_quiet():
        morning_report(d)
