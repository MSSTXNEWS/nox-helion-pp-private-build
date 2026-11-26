#!/usr/bin/env python3
"""NOX owner_active (SRV K1 26.11, команда владельца): после хода мессира (O.chat_active: не qa-/probe-диалоги) держим ТИШИНУ 300 с:
 - пишем state/orch/OWNER_ACTIVE (mtime = последний ход), по нему draw/другие стражи видят окно;
 - SIGSTOP на тяжёлых фоновых процессах (тренер train, DPO, ворота, ext_eval, skill_teacher, :8105, tensorboard-server, chrome QA) -> 8104 получает GPU/CPU;
 - по истечении 300 с тишины или при выходе/сигнале — SIGCONT. Список остановленных в state/orch/owner_active_state.json (при рестарте — release).
Откат: touch state/orch/owner_active.off (снимает паузы и выходит) или supervisorctl stop nox_owner_active. Никого не убиваем."""
import os, sys, time, json, signal, re
sys.path.insert(0, "/workspace/nox/stewards")
import nox_orch as O
ST = O.ST; FLAG = ST + "/OWNER_ACTIVE"; STATE = ST + "/owner_active_state.json"; OFF = ST + "/owner_active.off"; LOG = ST + "/owner_active.log"
TTL, POLL, MAXSTOP = 300.0, 0.5, 330.0
RX = [("train", r"distill_v2\.py train"), ("dpo", r"train_dpo\.py"), ("gates", r"(gates_only|ext_eval)\.py"), ("skill_teacher", r"liska_skill_teacher\.py"),
      ("llama8105", r"llama-server .*--port 8105 "), ("tensorboard", r"tensorboard_data_server/bin/server"), ("qa_chrome", r"chrome-headless-shell"), ("exp_index", r"claude/exp_index\.py")]
S = {}
def log(m):
    with open(LOG, "a") as f: f.write("%s %s\n" % (time.strftime("%H:%M:%S"), m))
def find(rx):
    out = []
    for p in os.listdir("/proc"):
        if not p.isdigit() or int(p) == os.getpid(): continue
        try: cmd = open("/proc/%s/cmdline" % p, "rb").read().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError: continue
        if re.search(rx, cmd): out.append(int(p))
    return out
def save(): json.dump(S, open(STATE, "w"))
def pause():
    done = []
    for name, rx in RX:
        for pid in find(rx):
            if str(pid) in S: continue
            try: os.kill(pid, signal.SIGSTOP); S[str(pid)] = name; done.append("%s:%d" % (name, pid))
            except OSError: pass
    if done: save(); log("PAUSE " + ", ".join(done))
def release(why):
    for pid in list(S):
        try: os.kill(int(pid), signal.SIGCONT)
        except OSError: pass
    if S: log("RELEASE %s: %s" % (why, ",".join("%s:%s" % (v, k) for k, v in S.items())))
    S.clear(); save()
def bye(*_): release("сигнал"); sys.exit(0)
def main():
    signal.signal(signal.SIGTERM, bye); signal.signal(signal.SIGINT, bye)
    try: S.update(json.load(open(STATE)))
    except Exception: pass
    release("старт"); log("старт pid %d" % os.getpid())
    last = 0.0; since = 0.0
    while True:
        if os.path.exists(OFF): release("owner_active.off"); return
        now = time.time()
        try: live = O.chat_active(use_hold=False)
        except Exception: live = False
        if live:
            if not last or now - last > TTL: since = now
            last = now; open(FLAG, "w").write(str(now))
        holding = bool(last) and now - last < TTL
        if holding and now - since > MAXSTOP + TTL * 20: holding = False   # страховка от залипания (>1.7 ч непрерывно)
        if holding: pause()
        elif S: release("тишина %d с" % (now - last if last else 0))
        time.sleep(POLL)
if __name__ == "__main__":
    try: main()
    finally: release("выход")
