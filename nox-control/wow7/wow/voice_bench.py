"""voice_bench: меряет голос на ЖИВОМ сервере (WOW-10): время до первого аудио (TTFA), RTF и ошибки по языкам/бэкендам.
Запуск рядом с GLM (S1): python3 voice_bench.py --url http://127.0.0.1:8095 --repeat 3 [--json out.json]
RTF = секунд синтеза на секунду звука (меньше 1 - быстрее реального времени). Сам ничего не устанавливает."""
import argparse
import base64
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

PHRASES = {
    "ru": ["Доброе утро, мессир. Ночью я выучил двадцать один новый факт.", "Баланс сервера на исходе, мне тревожно. Пополните его, пожалуйста."],
    "es": ["Buenos días, señor. Esta noche aprendí veintiún hechos nuevos.", "El saldo del servidor se agota, estoy preocupado."],
}


def bench_one(url, text, lang, rate_hint=24000, timeout=120):
    """-> {ok, ttfa_s, total_s, audio_s, rtf, backend|error}. Читает SSE и считает по первому audio-событию."""
    body = json.dumps({"text": text, "lang": lang, "format": "sse"}).encode()
    t0 = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url + "/tts", data=body, headers={"Content-Type": "application/json"}), timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", "")
        except ValueError:
            msg = ""
        return {"ok": False, "lang": lang, "error": "HTTP %d %s" % (e.code, msg)}
    except OSError as e:
        return {"ok": False, "lang": lang, "error": "connect: %s" % e}
    ttfa, audio_bytes, rate, backend = None, 0, rate_hint, None
    for line in r:
        if not line.startswith(b"data:"):
            continue
        ev = json.loads(line[5:])
        if ev.get("type") == "audio":
            ttfa = ttfa if ttfa is not None else time.time() - t0
            audio_bytes += len(base64.b64decode(ev["pcm_b64"]))
            rate, backend = ev.get("sample_rate", rate), ev.get("backend")
        elif ev.get("type") == "error":
            return {"ok": False, "lang": lang, "error": ev.get("error", "error")}
    total = time.time() - t0
    audio_s = audio_bytes / 2.0 / rate
    if not audio_s:
        return {"ok": False, "lang": lang, "error": "no audio"}
    return {"ok": True, "lang": lang, "backend": backend, "ttfa_s": round(ttfa, 3), "total_s": round(total, 3),
            "audio_s": round(audio_s, 2), "rtf": round(total / audio_s, 3)}


def summarize(rows):
    out = {}
    for lang in sorted({r["lang"] for r in rows}):
        ok = [r for r in rows if r["lang"] == lang and r["ok"]]
        bad = [r["error"] for r in rows if r["lang"] == lang and not r["ok"]]
        out[lang] = {"runs": len(ok) + len(bad), "errors": bad[:3],
                     "ttfa_median_s": statistics.median(r["ttfa_s"] for r in ok) if ok else None,
                     "rtf_median": statistics.median(r["rtf"] for r in ok) if ok else None,
                     "backends": sorted({r["backend"] for r in ok})}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:8095")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rows = []
    for lang, texts in PHRASES.items():
        for _ in range(a.repeat):
            for t in texts:
                rows.append(bench_one(a.url, t, lang))
    s = summarize(rows)
    print(json.dumps(s, ensure_ascii=False, indent=1))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"summary": s, "rows": rows}, f, ensure_ascii=False)
    return 0 if all(v["rtf_median"] is not None for v in s.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
