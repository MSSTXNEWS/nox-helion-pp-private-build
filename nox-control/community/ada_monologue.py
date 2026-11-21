"""Внутренний монолог: цикл «мысль» через базовый /completion llama-server (без чат-шаблона).

* Мысль = продолжение текстового промпта (личность + последние мысли). Пустая мысль = действие «молчать»;
  молчание допустимо и учитывается (kind=silence).
* Монолог хранится в JSONL (по строке на запись).
* Файлы личности только для чтения: SHA256 снимается при создании, проверяется ДО и ПОСЛЕ каждого цикла.
  Любое расхождение (изменён/удалён файл) -> блокировка (blocked=True), мысль цикла НЕ сохраняется,
  инцидент пишется в incidents-JSONL. Модуль никогда не открывает файлы личности на запись.
"""
import hashlib
import json
import os
import time
import urllib.request
import urllib.error

DEFAULT_URL = os.environ.get("NOX_LLAMA_URL", "http://127.0.0.1:8081")


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
    except OSError:
        return None
    return h.hexdigest()


class Blocked(RuntimeError):
    pass


class Monologue:
    def __init__(self, journal_path, persona_paths=(), url=None, incidents_path=None, n_predict=96,
                 temperature=0.9, history=8, timeout=60.0, stop=("\n\n",)):
        self.journal = journal_path
        self.persona_paths = [os.path.abspath(p) for p in persona_paths]
        self.url = (url or DEFAULT_URL).rstrip("/")
        self.incidents = incidents_path or (journal_path + ".incidents.jsonl")
        self.n_predict, self.temperature, self.history, self.timeout, self.stop = n_predict, temperature, history, timeout, list(stop)
        self.baseline = {p: sha256_file(p) for p in self.persona_paths}
        self.blocked = False
        self.block_reason = None
        self.stats = {"thoughts": 0, "silences": 0, "errors": 0}
        missing = [p for p, h in self.baseline.items() if h is None]
        if missing:
            self._block("persona file unreadable at start", {"files": missing})

    # ---- журнал
    @staticmethod
    def _append(path, rec):
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def read_journal(self, kinds=None):
        out = []
        if not os.path.exists(self.journal):
            return out
        with open(self.journal, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if kinds is None or r.get("kind") in kinds:
                    out.append(r)
        return out

    def _block(self, reason, details):
        self.blocked = True
        self.block_reason = reason
        self._append(self.incidents, {"ts": time.time(), "kind": "persona_integrity", "reason": reason, "details": details})

    def verify(self):
        """True если все файлы личности совпадают с базовыми хешами."""
        bad = []
        for p, h in self.baseline.items():
            cur = sha256_file(p)
            if cur != h:
                bad.append({"file": p, "expected": h, "actual": cur})
        if bad:
            self._block("persona hash mismatch", {"files": bad})
            return False
        return True

    # ---- промпт и модель
    def build_prompt(self):
        parts = []
        for p in self.persona_paths:
            with open(p, "r", encoding="utf-8", errors="replace") as f:  # только чтение
                parts.append(f.read().strip())
        thoughts = [r["text"] for r in self.read_journal({"thought"})][-self.history:]
        head = "\n\n".join(parts)
        body = "\n".join("- " + t.replace("\n", " ") for t in thoughts)
        return (head + "\n\n" if head else "") + "Внутренний монолог (мысли про себя; пустая строка = молчание):\n" + body + ("\n" if body else "") + "- "

    def _complete(self, prompt):
        data = json.dumps({"prompt": prompt, "n_predict": self.n_predict, "temperature": self.temperature,
                           "stop": self.stop, "stream": False, "cache_prompt": True}).encode()
        req = urllib.request.Request(self.url + "/completion", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))["content"]

    def think_once(self):
        """Один цикл. Возвращает запись журнала (dict) или None если заблокировано."""
        if self.blocked:
            return None
        if not self.verify():
            return None
        try:
            raw = self._complete(self.build_prompt())
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            self.stats["errors"] += 1
            rec = {"ts": time.time(), "kind": "error", "text": "", "error": str(e)[:300]}
            self._append(self.journal, rec)
            self.verify()
            return rec
        if not self.verify():  # после цикла
            return None
        text = (raw or "").strip().split("\n")[0].strip()
        if text:
            rec = {"ts": time.time(), "kind": "thought", "text": text}
            self.stats["thoughts"] += 1
        else:
            rec = {"ts": time.time(), "kind": "silence", "text": ""}
            self.stats["silences"] += 1
        self._append(self.journal, rec)
        return rec

    def run(self, cycles, interval=0.0, sleep=time.sleep):
        done = []
        for i in range(cycles):
            r = self.think_once()
            if r is None:
                break
            done.append(r)
            if interval and i < cycles - 1:
                sleep(interval)
        return done


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", required=True)
    ap.add_argument("--persona", action="append", default=[])
    ap.add_argument("--url", default=None)
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--interval", type=float, default=30.0)
    a = ap.parse_args()
    m = Monologue(a.journal, a.persona, a.url)
    for r in m.run(a.cycles, a.interval):
        print(json.dumps(r, ensure_ascii=False))
    if m.blocked:
        raise SystemExit("BLOCKED: " + str(m.block_reason))
