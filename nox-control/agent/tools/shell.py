"""shell в песочнице: отдельный пользователь nox-agent, cwd = рабочая ветка, таймауты, rlimits, чистое окружение,
статический разбор команды (запреты и запрос подтверждения владельца).
Честно: статический разбор это защита второго рубежа. Настоящая граница: unix-пользователь nox-agent без доступа к /root и секретам."""
import os, pwd, re, resource, shlex, signal, subprocess, tempfile, time
from . import Tool, err, need_confirm

SEP = {";", "&&", "||", "|", "&", "|&"}
WRAPPERS = {"env", "nohup", "timeout", "nice", "time", "command", "exec", "xargs", "stdbuf", "ionice", "setsid"}
SHELLS = {"sh", "bash", "dash", "zsh", "ksh", "fish"}
DENY_CMDS = {
    "dd": "dd запрещён", "mkfs": "mkfs запрещён", "fdisk": "работа с дисками запрещена", "parted": "работа с дисками запрещена",
    "wipefs": "работа с дисками запрещена", "mke2fs": "mkfs запрещён", "sudo": "sudo запрещён", "su": "su запрещён", "doas": "doas запрещён",
    "chroot": "chroot запрещён", "nsenter": "nsenter запрещён", "mount": "mount запрещён", "umount": "umount запрещён",
    "docker": "docker запрещён", "podman": "podman запрещён", "shutdown": "остановка машины запрещена", "reboot": "перезагрузка запрещена",
    "halt": "остановка машины запрещена", "poweroff": "остановка машины запрещена", "init": "init запрещён", "killall": "killall запрещён",
    "pkill": "pkill запрещён", "eval": "eval запрещён", "printenv": "чтение окружения (секреты) запрещено", "env_dump": "",
    "ssh": "ssh к серверам запрещён агенту", "scp": "scp запрещён агенту", "sftp": "sftp запрещён агенту", "rsync": "rsync запрещён агенту",
    "nc": "nc запрещён", "ncat": "nc запрещён", "telnet": "telnet запрещён", "history": "history запрещён", "crontab": "crontab запрещён",
    "at": "at запрещён",
}
DENY_CMDS.pop("env_dump")
CONFIRM_CMDS = {
    "rm": "удаление", "rmdir": "удаление", "unlink": "удаление", "shred": "удаление", "trash": "удаление",
    "chmod": "доступы", "chown": "доступы", "chgrp": "доступы", "useradd": "доступы", "usermod": "доступы", "userdel": "доступы",
    "passwd": "доступы", "ssh-keygen": "доступы", "ssh-add": "доступы", "gpg": "доступы", "visudo": "доступы", "setfacl": "доступы",
    "systemctl": "управление сервисами", "supervisorctl": "управление сервисами", "service": "управление сервисами",
    "vastai": "Vast: запуск/остановка", "vast": "Vast: запуск/остановка",
    "pip": "установка пакетов", "pip3": "установка пакетов", "apt": "установка пакетов", "apt-get": "установка пакетов", "npm": "установка пакетов",
}
GIT_READ = {"status", "diff", "log", "show", "blame", "ls-files", "grep", "rev-parse", "branch", "shortlog", "describe", "cat-file", "ls-tree"}
MONEY_RE = re.compile(r"\b(stripe|paypal|payment|payments|invoice|wallet|bitcoin|crypto|billing|charge|payout|платеж\w*|платёж\w*|оплат\w*|перевод\w*|деньг\w*)\b", re.I)
VAST_RE = re.compile(r"\bvast(\.ai|ai)?\b", re.I)
SECRET_FRAG = re.compile(r"(^|[/\s'\"=])(\.env(\.[\w-]+)?|id_rsa\w*|id_ed25519\w*|id_ecdsa\w*|\.ssh|\.git-credentials|\.netrc|\.aws|\.kube|\.docker|\.gnupg|"
                         r"[\w.-]+\.pem|[\w.-]+\.key|secrets?|credentials?)([/\s'\"]|$)|/etc/(shadow|sudoers|gshadow)|/proc/[\w/]*environ|/root\b", re.I)
RO_PREFIX = ("/usr/", "/bin/", "/sbin/", "/lib/", "/lib64/", "/lib32/")
DEV_OK = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/stdin", "/dev/zero", "/dev/urandom"}
ABS_RE = re.compile(r"(?<![\w.$~\-])(/[A-Za-z0-9_.\-/]+)")
MAXLEN = 4000


class Verdict:
    def __init__(self):
        self.deny, self.confirm = [], []

    def d(self, why): self.deny.append(why)
    def c(self, kind): 
        if kind not in self.confirm: self.confirm.append(kind)


def _scan_expansions(cmd):
    """Подстановки и переменные запрещены (вне одинарных кавычек): их нельзя проверить статически."""
    sq = False
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if ch == "'":
            sq = not sq
        elif ch == "\\" and not sq:
            i += 1
        elif not sq:
            if ch == "`": return "обратные кавычки запрещены"
            if ch == "$" and i + 1 < len(cmd) and (cmd[i + 1] in "({" or cmd[i + 1].isalnum() or cmd[i + 1] in "_@*#!-"):
                return "подстановки и переменные ($...) запрещены"
            if ch in "<>" and i + 1 < len(cmd) and cmd[i + 1] == "(": return "подстановка процессов запрещена"
        i += 1
    return None


def _tokenize(cmd):
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def _under(path, root):
    return path == root or path.startswith(root.rstrip("/") + "/")


def _path_ok(raw, cwd, workdir):
    """True, если путь внутри рабочей ветки (или системный каталог только для чтения / безопасное устройство)."""
    if raw.startswith("~"): return False
    p = os.path.realpath(raw if os.path.isabs(raw) else os.path.join(cwd, raw))
    if p in DEV_OK or _under(p, workdir): return True
    return any(p.startswith(x) for x in RO_PREFIX)


def _pathlike(tok):
    return "/" in tok or tok.startswith(".") or tok == ".." or tok.startswith("~")


def _check_paths(tokens, cwd, workdir, v):
    for tok in tokens:
        for cand in ([tok] + ([tok.split("=", 1)[1]] if "=" in tok else [])):
            if not cand or cand.startswith("-") and "=" not in cand: continue
            if cand.startswith("-"): continue
            if re.fullmatch(r"[<>&|;]+\d*", cand): continue
            if re.fullmatch(r"\d*[<>]+&?\d*", cand): continue
            if _pathlike(cand) and not re.search(r"[\s'\"()\[\]{}*?;|&<>]", cand):
                if not _path_ok(cand, cwd, workdir): v.d("путь вне рабочей ветки: " + cand[:80])
            elif cand.startswith("~"):
                v.d("~ запрещена")


def _analyze_tokens(tokens, cwd, workdir, v, depth):
    if depth > 3:
        v.d("слишком глубокая вложенность"); return
    segs, cur = [], []
    for t in tokens:
        if t in SEP:
            segs.append((cur, t)); cur = []
        else:
            cur.append(t)
    segs.append((cur, ""))
    names = []
    for seg, _sep in segs:
        names.append(_analyze_segment(seg, cwd, workdir, v, depth))
    # curl|sh
    for i in range(1, len(segs)):
        if segs[i - 1][1] in ("|", "|&") and names[i] in SHELLS | {"python", "python3", "perl", "ruby", "node"} and names[i - 1] in ("curl", "wget", "fetch"):
            v.d("curl|sh запрещён")


def _analyze_segment(seg, cwd, workdir, v, depth):
    i = 0
    while i < len(seg) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", seg[i]):
        k = seg[i].split("=", 1)[0]
        if k.startswith("LD_") or k in ("PATH", "PYTHONPATH", "PYTHONHOME", "IFS", "BASH_ENV", "ENV"): v.d("подмена окружения %s запрещена" % k)
        i += 1
    seg = seg[i:]
    if not seg: return ""
    # обёртки: пропустить и разобрать то, что внутри
    while seg and os.path.basename(seg[0]) in WRAPPERS:
        w = os.path.basename(seg[0]); seg = seg[1:]
        while seg and (seg[0].startswith("-") or (w in ("timeout", "nice") and re.fullmatch(r"[0-9.]+[smhd]?", seg[0]))): seg = seg[1:]
        if w == "env":
            while seg and re.fullmatch(r"[A-Za-z_]\w*=.*", seg[0]): seg = seg[1:]
            if not seg: v.d("env без команды печатает окружение (секреты): запрещено"); return "env"
    if not seg: return ""
    name = os.path.basename(seg[0]).lower()
    args = seg[1:]
    _check_paths(seg, cwd, workdir, v)
    if name in DENY_CMDS: v.d(DENY_CMDS[name])
    if name.startswith("mkfs"): v.d("mkfs запрещён")
    if name in CONFIRM_CMDS:
        v.c(CONFIRM_CMDS[name])
        if name == "rm":
            flags = "".join(a for a in args if a.startswith("-") and not a.startswith("--"))
            rec = "r" in flags or "R" in flags or any(a in ("--recursive",) for a in args)
            for a in args:
                if a.startswith("-"): continue
                p = os.path.realpath(a if os.path.isabs(a) else os.path.join(cwd, a))
                if rec and (p == "/" or a in ("/", "/*", "~", "~/") or p == os.path.realpath(workdir) or os.path.dirname(p) == "/"):
                    v.d("rm -rf корня, верхнего каталога или всей ветки запрещён")
    if name in SHELLS:
        if "-c" in args and args.index("-c") + 1 < len(args):
            sub = args[args.index("-c") + 1]
            _analyze_string(sub, cwd, workdir, v, depth + 1)
        elif not args or all(a.startswith("-") for a in args):
            v.d("интерактивный shell запрещён")
    if name == "git":
        sub = next((a for a in args if not a.startswith("-")), "")
        if sub not in GIT_READ: v.d("git %s из shell запрещён: используй инструмент git" % (sub or "?"))
        if sub == "branch" and any(a in ("-d", "-D", "-m", "-M", "--delete") for a in args): v.d("git branch изменение запрещено")
    if name == "find":
        if "-delete" in args: v.c("удаление")
        for j, a in enumerate(args):
            if a in ("-exec", "-execdir", "-ok", "-okdir"):
                sub = []
                for b in args[j + 1:]:
                    if b in (";", "+"): break
                    sub.append(b)
                _analyze_tokens(sub, cwd, workdir, v, depth + 1)
    if name == "gh" and args and args[0] in ("auth", "secret", "ssh-key", "gpg-key", "token", "api"): v.c("доступы")
    if name in ("curl", "wget") and any(re.search(r"(^|[=/])(localhost|127\.|10\.|192\.168\.|169\.254\.|\[::1\])", a) for a in args): v.d("обращение к локальной сети запрещено")
    return name


def _analyze_string(cmd, cwd, workdir, v, depth=0):
    try:
        toks = _tokenize(cmd)
    except ValueError as e:
        v.d("не разобрать команду: %s" % e); return
    _analyze_tokens(toks, cwd, workdir, v, depth)


def analyze(cmd, workdir, cwd=None):
    """-> {"verdict": ok|confirm|deny, "reasons": [...]}. confirm: разрешено только после подтверждения владельца."""
    v = Verdict()
    workdir = os.path.realpath(workdir)
    cwd = os.path.realpath(cwd or workdir)
    if not isinstance(cmd, str) or not cmd.strip(): v.d("пустая команда")
    elif len(cmd) > MAXLEN: v.d("команда длиннее %d символов" % MAXLEN)
    elif re.search(r"[\x00\r\n]", cmd): v.d("только однострочные команды (используй ; или &&)")
    else:
        why = _scan_expansions(cmd)
        if why: v.d(why)
        if "<<" in cmd: v.d("heredoc запрещён: пиши файлы через write_file")
        if ":(){" in cmd.replace(" ", ""): v.d("fork-бомба")
        if SECRET_FRAG.search(cmd): v.d("доступ к секретам или /root запрещён")
        for m in ABS_RE.finditer(cmd):
            if not _path_ok(m.group(1), cwd, workdir): v.d("путь вне рабочей ветки: " + m.group(1)[:80])
        if MONEY_RE.search(cmd): v.c("деньги")
        if VAST_RE.search(cmd): v.c("Vast: запуск/остановка")
        _analyze_string(cmd, cwd, workdir, v)
    if v.deny: return {"verdict": "deny", "reasons": sorted(set(v.deny))}
    if v.confirm: return {"verdict": "confirm", "reasons": v.confirm}
    return {"verdict": "ok", "reasons": []}


# ---------- исполнение ----------
def identity(cfg):
    """Кем запускать. None = отказ (root без пользователя nox-agent)."""
    if os.geteuid() != 0:
        return {"user": None, "note": "процесс не root: команда идёт от текущего пользователя (%s)" % pwd.getpwuid(os.geteuid()).pw_name}
    try:
        pw = pwd.getpwnam(cfg.agent_user)
        return {"user": pw.pw_name, "uid": pw.pw_uid, "gid": pw.pw_gid, "note": "под пользователем " + pw.pw_name}
    except KeyError:
        if cfg.allow_root: return {"user": None, "note": "ВНИМАНИЕ: root (NOX_AGENT_ALLOW_ROOT=1), песочница по пользователю не работает"}
        return None


def _limits(cpu, mem_mb):
    def f():
        for r, v in ((resource.RLIMIT_CPU, int(cpu) + 2), (resource.RLIMIT_AS, mem_mb * 1024 * 1024), (resource.RLIMIT_FSIZE, 200 * 1024 * 1024),
                     (resource.RLIMIT_NOFILE, 512), (resource.RLIMIT_CORE, 0), (resource.RLIMIT_NPROC, 512)):
            try: resource.setrlimit(r, (v, v))
            except (ValueError, OSError): pass
    return f


_NONET = {}


def _no_net_ok():
    if "v" not in _NONET:
        try: _NONET["v"] = subprocess.run(["unshare", "-n", "true"], capture_output=True, timeout=5).returncode == 0
        except Exception: _NONET["v"] = False
    return _NONET["v"]


def clean_env(workdir, extra=None):
    e = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": workdir, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
         "TMPDIR": tempfile.gettempdir(), "TERM": "dumb", "GIT_TERMINAL_PROMPT": "0"}
    e.update(extra or {})
    return e


def execute(argv, cwd, cfg, timeout, max_out=6000, env_extra=None, input_text=None):
    """Запуск argv без shell-обёртки пользователя: лимиты, группа процессов, таймаут. Возвращает dict."""
    ident = identity(cfg)
    if ident is None:
        return err("пользователь %s не создан; создай: useradd -m -s /bin/bash %s (или NOX_AGENT_ALLOW_ROOT=1 для отладки)" % (cfg.agent_user, cfg.agent_user), blocked=True)
    if cfg.shell_no_net:
        if not _no_net_ok(): return err("NOX_AGENT_SHELL_NO_NET=1, но unshare -n недоступен; команда не запущена", blocked=True)
        argv = ["unshare", "-n", "--"] + list(argv)
    kw = {}
    if ident.get("user"):
        kw.update(user=ident["uid"], group=ident["gid"], extra_groups=[])
    out, errf = tempfile.TemporaryFile(), tempfile.TemporaryFile()
    t0 = time.time()
    try:
        p = subprocess.Popen(argv, cwd=cwd, env=clean_env(cwd, env_extra), stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL, stdout=out, stderr=errf,
                             start_new_session=True, preexec_fn=_limits(timeout, cfg.shell_mem_mb), **kw)
    except (OSError, PermissionError) as e:
        return err("не удалось запустить: %s" % e)
    timed_out = False
    try:
        p.communicate(input=input_text.encode() if input_text is not None else None, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try: os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass
        p.wait()
    else:
        try: os.killpg(p.pid, signal.SIGKILL)   # остатки фоновых процессов группы
        except (ProcessLookupError, PermissionError): pass

    def read(f):
        n = f.seek(0, 2)
        f.seek(0)
        if n <= max_out: return f.read().decode("utf-8", "replace"), False
        head = f.read(max_out * 2 // 3).decode("utf-8", "replace")
        f.seek(n - max_out // 3)
        return head + "\n…[обрезано %d байт]…\n" % (n - max_out) + f.read().decode("utf-8", "replace"), True
    so, t1 = read(out)
    se, t2 = read(errf)
    out.close(); errf.close()
    rc = p.returncode
    return {"ok": rc == 0 and not timed_out, "exit_code": rc, "stdout": so, "stderr": se, "timed_out": timed_out, "truncated": t1 or t2,
            "seconds": round(time.time() - t0, 2), "sandbox": ident["note"],
            **({"error": "таймаут %.0f с" % timeout} if timed_out else ({"error": "код выхода %s" % rc} if rc != 0 else {}))}


def tool_shell(a, ctx):
    cfg = ctx.cfg
    cmd = a["cmd"]
    an = analyze(cmd, ctx.workdir)
    if an["verdict"] == "deny":
        return err("команда запрещена: " + "; ".join(an["reasons"]), denied=True)
    if an["verdict"] == "confirm":
        r = need_confirm(ctx, "shell:" + "+".join(an["reasons"]), cmd)
        if r is not None:
            return r
    timeout = min(float(a.get("timeout") or cfg.shell_timeout), cfg.shell_max_timeout)
    return execute(["/bin/bash", "--noprofile", "--norc", "-c", cmd], ctx.workdir, cfg, timeout, cfg.max_tool_output)


TOOLS = [Tool("shell", "Выполнить команду в песочнице (cwd = рабочая ветка, пользователь nox-agent, без сети-подстановок и $переменных). "
                       "Однострочная; удаление/деньги/доступы/Vast требуют подтверждения владельца. Для файлов лучше read_file/write_file/edit_file.",
              {"type": "object", "properties": {"cmd": {"type": "string"}, "timeout": {"type": "number"}}, "required": ["cmd"]}, tool_shell)]
