"""Фильтр воспоминаний перед подачей в модель: убирает технический мусор S03 (логи, пути, квитанции, хэши, служебные ключи)."""
import re
_JUNK = re.compile(r"(/root|/dev/|\.gguf|\.py\b|\.sh\b|\.json|https?://|GPU|OOM|swap|Q[2-8]_K|ftype|schema|receipt|RECEIPT|status:|name_en|role:|"
                   r"llama|ctrl\+c|/exit|/regen|supervisor|verify|pass\b|\bS[0-9]-|\b[0-9a-f]{8}\b|[{}<>\[\]=_]{2,}|\bid[:=])", re.I)
_PREFIX = re.compile(r"^\s*[0-9a-f]{6,}:\s*")
def clean(items, limit=5, maxlen=220):
    out, seen = [], set()
    for x in items or []:
        t = _PREFIX.sub("", str(x)).strip()
        if len(t) < 4 or len(t) > maxlen or _JUNK.search(t): continue
        k = t.lower()[:60]
        if k in seen: continue
        seen.add(k); out.append(t)
        if len(out) >= limit: break
    return out
def clean_text(text, limit=8):
    return "\n".join(clean([l.strip("-• ").strip() for l in (text or "").split("\n")], limit=limit))
