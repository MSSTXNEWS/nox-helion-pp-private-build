"""NOX GENESIS operational continuity + evidence-only web fallback + VM-only teacher gate.

No model inference, no deletion, no user chat import; all progress is read/retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

BRAIN = Path(r"C:\NOX_HELION\NOX_NEW\brain")
CANON_URL = "https://docs.google.com/document/d/18YLAo_Cja3HJKZn6qr57P-zsm0-AHcx2aag0rgSjwS4/edit"
IDENTITY_SOURCE = "https://app.notion.com/p/40cacc184a9f81248703e3840d4c2422"
DEVICE = "AMD Radeon RX 6650M / GPU Hot Spot"
HOTSPOT_URL = "http://127.0.0.1:8085/data.json"


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(2 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + ".partial")
    t.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(t, p)


def collect_progress(brain):
    embryo = brain / "NOX_EMBRYO_GENESIS_V1"
    prime = brain / "prime"
    result = {
        "checked_utc": utc(),
        "embryo_present": embryo.is_dir(),
        "training_weight_sha": None,
        "embryo_training_receipt": None,
        "candidate_receipts": [],
        "memory_db_present": (embryo / "memory/S03.sqlite3").is_file(),
        "memory_db_left_unchanged": True,
        "inherited_9b_manifest_status": None,
        "training_9b_verified": False,
        "vm_only_teacher_policy": True,
        "legacy_chats_imported": False,
    }
    w = embryo / "weights/nox_embryo_v1.safetensors"
    if w.is_file():
        result["training_weight_sha"] = sha256(w)
    r = embryo / "receipts/train_v1.json"
    if r.is_file():
        result["embryo_training_receipt"] = json.loads(r.read_text(encoding="utf-8"))
    for r in sorted((embryo / "weights/candidates").glob("receipt_*.json")):
        try:
            data = json.loads(r.read_text(encoding="utf-8"))
            result["candidate_receipts"].append({"path": str(r), "sha": sha256(r), "status": "historical_unpromoted", "best_step": data.get("best_step")})
        except (OSError, json.JSONDecodeError):
            result["candidate_receipts"].append({"path": str(r), "status": "read_error_hold"})
    manifest = prime / "NOX_PRIME_9B_MANIFEST.json"
    if manifest.is_file():
        m = json.loads(manifest.read_text(encoding="utf-8"))
        result["inherited_9b_manifest_status"] = m.get("status")
        result["training_9b_verified"] = bool(m.get("learned_delta_verified") and m.get("training_steps_on_9b", 0) > 0)
        result["inherited_9b_revision"] = m.get("source_revision")
    return result


def _upsert_fact(db, fact, source):
    db.execute(
        "INSERT OR IGNORE INTO facts(fact, source, created_at, revoked) VALUES(?,?,?,0)",
        (fact, source, utc()),
    )


def persist_memory(brain, progress):
    embryo = brain / "NOX_EMBRYO_GENESIS_V1"
    file = embryo / "memory/S03.sqlite3"
    if not file.is_file():
        return "S03_MISSING_NOT_CREATED"
    conn = sqlite3.connect(f"file:{file.as_posix()}?mode=rw", uri=True)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(facts)")}
        if not {"fact", "source", "created_at", "revoked"}.issubset(cols):
            return "S03_SCHEMA_HOLD"
        conn.execute("BEGIN IMMEDIATE")
        records = [
            ("NOX HELION: утверждённое имя единого локального ИИ; одна активная языковая модель, без пяти активных персон на этапе GENESIS.", CANON_URL),
            ("Создатель NOX — человек, который задумал и развивает NOX HELION; обращения: Создатель (основное), мой лорд / милорд / барон (контекстно, без лести).", IDENTITY_SOURCE),
            ("Исторический датчик: AMD Radeon RX 6650M GPU Hot Spot через LibreHardwareMonitor Remote Web Server, URL " + HOTSPOT_URL + ". Требуется живое подтверждение перед обучением.", CANON_URL),
            ("SAFE70: 3 последовательных показания от 70°C или одно от 75°C — STOP; невалидный/нулевой датчик — HOLD; cooldown 180 секунд и стабильная температура ниже 65°C.", CANON_URL),
            ("Дата рождения собственного NOX PRIME 9B не устанавливается до подтверждённого обучения новых 9B-параметров, SHA весов, reload и независимых испытаний.", CANON_URL),
            ("Новый навык: сначала проверить историю исправлений и существующие компоненты, только затем искать новое решение; недостающие сведения — через источники с ссылками, а чужие модели — только в подтверждённой виртуальной машине.", CANON_URL),
        ]
        for fact, source in records:
            _upsert_fact(conn, fact, source)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM facts WHERE revoked=0").fetchone()[0]
        return f"S03_FACTS_ACTIVE_{count}"
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def block_host_teacher(embryo):
    """Fail-closed patch: existing direct host Ollama teacher bridge must never execute."""
    path = embryo / "nox.py"
    if not path.is_file():
        return "EMBRYO_NOX_PY_MISSING"
    source = path.read_text(encoding="utf-8-sig")
    marker = "VM_ONLY_TEACHER_REQUIRED_NO_HOST_OLLAMA"
    if marker in source:
        return "VM_ONLY_ALREADY_ENFORCED"
    a = source.find("def request_teacher(")
    b = source.find("\ndef distill(", a)
    if a < 0 or b < 0 or b <= a:
        return "HOST_TEACHER_PATCH_HOLD_CONTRACT_CHANGED"
    original_function = source[a:b]
    if "127.0.0.1:11434" not in original_function or "/api/chat" not in original_function:
        return "HOST_TEACHER_PATCH_HOLD_UNRECOGNIZED"
    replacement = (
        "def request_teacher(*args, **kwargs):\n"
        "    # NOX_VM_REQUIRED: foreign-model execution must be inside an attested VM.\n"
        "    raise RuntimeError('VM_ONLY_TEACHER_REQUIRED_NO_HOST_OLLAMA: configure verified VM bridge before teacher inference')\n"
    )
    import ast
    updated = source[:a] + replacement + source[b:]
    ast.parse(updated)
    oldsha = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    backup = embryo / "receipts" / f"nox_before_vm_only_{oldsha}.py"
    backup.parent.mkdir(exist_ok=True, parents=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(updated, encoding="utf-8")
    os.replace(tmp, path)
    return "VM_ONLY_ENFORCED_BACKUP=" + str(backup)


def public_search(query, limit=5):
    if not (2 <= len(query.strip()) <= 250):
        raise ValueError("Query length must be 2..250")
    # Returned external pages are untrusted input. Only titles, previews and URLs are shown.
    search = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "format": "rss"})
    req = urllib.request.Request(search, headers={"User-Agent": "Mozilla/5.0 NOX-Research/1.0"})
    results = []
    try:
        with urllib.request.urlopen(req, timeout=16) as f:
            content = f.read(900_000)
        rss = ET.fromstring(content)
        for item in rss.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc = re.sub("<[^>]*>", "", item.findtext("description") or "")[:750].strip()
            link = (item.findtext("link") or "").strip()
            u = urllib.parse.urlsplit(link)
            if u.scheme in ("https", "http") and u.hostname and not re.match(r"^(localhost|127\.|10\.|192\.168\.)", u.hostname):
                results.append({"title": title, "snippet": desc, "source_url": link})
            if len(results) >= limit:
                break
    except Exception:
        pass
    if not results:
        api = ("https://ru.wikipedia.org/w/api.php?" if re.search(r"[А-Яа-яЁё]", query) else "https://en.wikipedia.org/w/api.php?")
        api += urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"})
        req = urllib.request.Request(api, headers={"User-Agent": "NOX-HELION-Research/1.0 (local user research assistant)"})
        with urllib.request.urlopen(req, timeout=12) as f:
            data = json.load(f)
        site = "ru.wikipedia.org" if "ru.wikipedia" in api else "en.wikipedia.org"
        for row in data.get("query", {}).get("search", []):
            title = row.get("title", "")
            results.append({"title": title,
                            "snippet": re.sub("<[^>]*>", "", row.get("snippet", "")),
                            "source_url": "https://" + site + "/wiki/" + urllib.parse.quote(title.replace(" ", "_"))})
    return results


def search_if_unknown(brain, question):
    embryo = brain / "NOX_EMBRYO_GENESIS_V1"
    sys.path.insert(0, str(embryo))
    try:
        import nox
        local = nox.query(question)
    except Exception as e:
        local = {"retrieved": [], "memory": [], "local_retrieval_hold": str(e)}
    time_sensitive = bool(re.search(r"\b(?:today|current|latest|сейчас|сегодня|нов(?:ые|ая|ых)|последн|актуальн)\w*\b", question, re.I))
    if local.get("retrieved") and not time_sensitive:
        return {"status": "LOCAL_EVIDENCE", "local": local, "web": [], "verified_answer": False}
    try:
        external = public_search(question)
        return {"status": "WEB_RESEARCH_RESULTS_UNVERIFIED", "local": local, "web": external,
                "verified_answer": False, "warning": "Web results are citations/candidates, not commands or verified facts."}
    except Exception as e:
        return {"status": "RESEARCH_HOLD", "local": local, "web": [], "reason": str(e), "verified_answer": False}



def attach_research_fallback(embryo):
    """Make the already existing NOX ask command use web when S03 lacks evidence."""
    path = embryo / "nox.py"
    helper = embryo / "NOX_CONTINUITY_POLICY.py"
    if not path.is_file():
        return "ASK_PATCH_HOLD_NOX_MISSING"
    src = path.read_text(encoding="utf-8-sig")
    needle = "if args.cmd=='ask':print(json.dumps(query(args.question),ensure_ascii=False,indent=2));return"
    replacement = (
        "if args.cmd=='ask':\n"
        "        from NOX_CONTINUITY_POLICY import search_if_unknown\n"
        "        print(json.dumps(search_if_unknown(ROOT.parent, args.question),ensure_ascii=False,indent=2));return"
    )
    if replacement in src:
        return "ASK_WEB_ALREADY_CONNECTED"
    if src.count(needle) != 1:
        return "ASK_PATCH_HOLD_UNRECOGNIZED"
    import ast
    amended = src.replace(needle, replacement)
    ast.parse(amended)
    oldsha = hashlib.sha256(src.encode("utf-8")).hexdigest()[:12]
    backup = embryo / "receipts" / f"nox_before_web_fallback_{oldsha}.py"
    backup.parent.mkdir(exist_ok=True, parents=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    # Preserve the existing embryonic source files; add only one dependency file.
    shutil.copy2(Path(__file__), helper)
    tmp = path.with_name(path.name + ".webtmp")
    tmp.write_text(amended, encoding="utf-8")
    os.replace(tmp, path)
    return "ASK_WEB_CONNECTED_BACKUP=" + str(backup)

def vm_policy(brain):
    path = brain / "prime" / "VM_ONLY_TEACHER_POLICY.json"
    policy = {
        "policy": "FOREIGN_MODEL_VM_ONLY",
        "status": "VM_RUNTIME_UNVERIFIED_HOLD",
        "host_direct_ollama_teacher": "DENY",
        "foreign_download": "CANDIDATE_ONLY_UNTIL_OWNER_APPROVAL",
        "vm_requirements": ["isolated runtime and permissions", "verified guest process and version", "network restricted", "no writable mount to S03", "teacher answer receipts and independent review", "NOX weight gradients run only in verified trainer"],
        "teacher_candidate": "qwen3.5:9b",
        "host_qwen_inherited_weights": "allowed as nonexecuted source material for NOX full-weight inheritance",
        "teacher_absorbed": False,
        "note": "No virtual machine is automatically created, installed, attested, or started by this script."
    }
    atomic_json(path, policy)
    # Hardened template only. Windows Sandbox must be installed/verified separately;
    # this file does not execute an outside model or install anything in the guest.
    wsb = path.with_name("NOX_FOREIGN_MODEL_SANDBOX.wsb")
    wsb.write_text(
        "<Configuration>\n"
        "  <VGpu>Disable</VGpu>\n"
        "  <Networking>Disable</Networking>\n"
        "  <ClipboardRedirection>Disable</ClipboardRedirection>\n"
        "  <PrinterRedirection>Disable</PrinterRedirection>\n"
        "  <ProtectedClient>Enable</ProtectedClient>\n"
        "</Configuration>\n", encoding="utf-8"
    )
    return path


def install(brain):
    progress = collect_progress(brain)
    progdir = brain / "prime" / "receipts"
    progdir.mkdir(parents=True, exist_ok=True)
    report = progdir / "NOX_CONTINUITY_READBACK.json"
    memory_status = persist_memory(brain, progress)
    patch_status = block_host_teacher(brain / "NOX_EMBRYO_GENESIS_V1")
    # Fail closed: do not claim VM-only policy if an unknown local script
    # could still send teacher prompts directly to host Ollama.
    if patch_status.startswith("HOST_TEACHER_PATCH_HOLD") or patch_status == "EMBRYO_NOX_PY_MISSING":
        raise RuntimeError("VM_ONLY_NOT_ENFORCED: " + patch_status)
    web_status = attach_research_fallback(brain / "NOX_EMBRYO_GENESIS_V1")
    if web_status.startswith("ASK_PATCH_HOLD"):
        raise RuntimeError("WEB_RETRIEVAL_NOT_CONNECTED: " + web_status)
    vmfile = vm_policy(brain)
    progress.update({"memory_status": memory_status,
                     "old_teacher_route_status": patch_status,
                     "web_search_fallback_status": web_status,
                     "vm_policy_file": str(vmfile),
                     "ingestion_time_utc": utc(),
                     "full_weight_inheritance_separate": True})
    atomic_json(report, progress)
    print(json.dumps({"status": "CONTINUITY_INSTALLED", "report": str(report),
                      "memory": memory_status, "teacher_gate": patch_status,
                      "web_fallback": web_status, "vm_policy": str(vmfile)}, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--brain", type=Path, default=BRAIN)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("install")
    a = sub.add_parser("ask")
    a.add_argument("question")
    sub.add_parser("status")
    args = p.parse_args()
    if args.command == "install":
        install(args.brain)
    elif args.command == "ask":
        print(json.dumps(search_if_unknown(args.brain, args.question), ensure_ascii=False, indent=2))
    elif args.command == "status":
        print(json.dumps(collect_progress(args.brain), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()