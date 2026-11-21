"""Конфигурация агента NOX: всё через переменные окружения (NOX_AGENT_*). Только stdlib."""
import os, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.dirname(os.path.dirname(HERE))   # корень репозитория (../.. от nox-control/agent)


def _int(e, k, d):
    try: return int(e.get(k, d))
    except (TypeError, ValueError): return int(d)


def _float(e, k, d):
    try: return float(e.get(k, d))
    except (TypeError, ValueError): return float(d)


def _list(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _state_default():
    """/root/nox/state/agent на сервере NOX (если /root/nox/state существует и доступен), иначе каталог во временной папке. Ничего не создаёт."""
    if os.access("/root/nox/state", os.W_OK): return "/root/nox/state/agent"
    return os.path.join(tempfile.gettempdir(), "nox-agent-state")


class Config:
    """Читает env при создании; kw переопределяют (для тестов)."""

    def __init__(self, env=None, **kw):
        e = os.environ if env is None else env
        self.gateway = e.get("NOX_AGENT_GATEWAY", "http://127.0.0.1:8082").rstrip("/")
        self.mode = e.get("NOX_AGENT_MODE", "deep")            # nox_mode основного цикла
        self.judge_mode = e.get("NOX_AGENT_JUDGE_MODE", "fast")  # быстрый тир для судьи
        self.call_timeout = _float(e, "NOX_AGENT_CALL_TIMEOUT", 900)
        self.max_steps = _int(e, "NOX_AGENT_MAX_STEPS", 30)
        self.max_seconds = _float(e, "NOX_AGENT_MAX_SECONDS", 1800)
        self.max_tokens = _int(e, "NOX_AGENT_MAX_TOKENS", 200000)       # сумма total_tokens по всем вызовам
        self.step_max_tokens = _int(e, "NOX_AGENT_STEP_MAX_TOKENS", 4096)
        self.ctx_chars = _int(e, "NOX_AGENT_CTX_CHARS", 36000)           # порог сжатия истории
        self.plan_phase = e.get("NOX_AGENT_PLAN", "1") not in ("0", "false", "off")
        self.stuck_limit = _int(e, "NOX_AGENT_STUCK", 3)                 # подряд одинаковых ошибок
        self.verify_retries = _int(e, "NOX_AGENT_VERIFY_RETRIES", 2)
        self.max_tool_output = _int(e, "NOX_AGENT_TOOL_OUTPUT", 6000)
        self.state_dir = e.get("NOX_AGENT_STATE", "") or _state_default()
        self.stop_file = e.get("NOX_AGENT_STOP_FILE", "") or os.path.join(self.state_dir, "STOP")
        self.log_dir = e.get("NOX_AGENT_LOG_DIR", "") or os.path.join(self.state_dir, "journal")
        self.approvals_file = e.get("NOX_AGENT_APPROVALS", "") or os.path.join(self.state_dir, "approvals.jsonl")
        self.repo = e.get("NOX_AGENT_REPO", "") or DEFAULT_REPO           # живой репозиторий (main)
        self.base_branch = e.get("NOX_AGENT_BASE_BRANCH", "main")
        self.work_root = e.get("NOX_AGENT_WORK", "") or os.path.join(self.state_dir, "work")
        self.agent_user = e.get("NOX_AGENT_USER", "nox-agent")
        self.allow_root = e.get("NOX_AGENT_ALLOW_ROOT", "0") in ("1", "true")   # запуск shell от root без nox-agent (только для отладки)
        self.shell_timeout = _float(e, "NOX_AGENT_SHELL_TIMEOUT", 60)
        self.shell_max_timeout = _float(e, "NOX_AGENT_SHELL_MAX_TIMEOUT", 600)
        self.shell_mem_mb = _int(e, "NOX_AGENT_SHELL_MEM_MB", 1024)
        self.shell_no_net = e.get("NOX_AGENT_SHELL_NO_NET", "0") in ("1", "true")
        self.test_cmd = e.get("NOX_AGENT_TEST_CMD", "python3 -m unittest discover -s agent -t . -p test_*.py")
        self.test_cwd = e.get("NOX_AGENT_TEST_CWD", "nox-control")     # относительно рабочей ветки
        self.test_timeout = _float(e, "NOX_AGENT_TEST_TIMEOUT", 900)
        self.proxy = e.get("NOX_AGENT_HTTP_PROXY", "") or e.get("HTTPS_PROXY", "") or e.get("https_proxy", "")
        self.search_url = e.get("NOX_AGENT_SEARCH_URL", "https://html.duckduckgo.com/html/")
        self.search_kind = e.get("NOX_AGENT_SEARCH_KIND", "ddg")          # ddg | searx
        self.web_timeout = _float(e, "NOX_AGENT_WEB_TIMEOUT", 20)
        self.web_max_bytes = _int(e, "NOX_AGENT_WEB_MAX_BYTES", 1000000)
        self.web_max_chars = _int(e, "NOX_AGENT_WEB_MAX_CHARS", 8000)
        self.web_per_run = _int(e, "NOX_AGENT_WEB_PER_RUN", 20)          # лимит веб-вызовов за прогон
        self.allow_private_fetch = e.get("NOX_AGENT_ALLOW_PRIVATE_FETCH", "0") in ("1", "true")
        self.git_pass_env = _list(e.get("NOX_AGENT_GIT_PASS_ENV", "GH_TOKEN,GITHUB_TOKEN,GIT_ASKPASS,SSH_AUTH_SOCK,HOME"))
        self.remote = e.get("NOX_AGENT_REMOTE", "origin")
        self.health_url = e.get("NOX_AGENT_HEALTH_URL", "http://127.0.0.1:8082/v1/nox/stats")
        self.health_checks = _int(e, "NOX_AGENT_HEALTH_CHECKS", 3)
        self.health_interval = _float(e, "NOX_AGENT_HEALTH_INTERVAL", 5)
        self.deploy_cmd = e.get("NOX_AGENT_DEPLOY_CMD", "")             # необязательно: перезапуск после merge (argv без shell)
        self.merge = e.get("NOX_AGENT_MERGE", "1") not in ("0", "false", "off")
        self.judge_max_diff = _int(e, "NOX_AGENT_JUDGE_MAX_DIFF", 24000)
        self.protected = _list(e.get("NOX_AGENT_PROTECTED", "nox-control/agent/release.py,nox-control/agent/tools/approvals.py,"
                                     "nox-control/agent/tools/shell.py,nox-control/agent/tools/files.py,nox-control/agent/tools/gitops.py,.github/*"))
        self.inbox = e.get("NOX_AGENT_INBOX", "/root/nox/state/dispatcher/owner_inbox.jsonl")
        self.queue = e.get("NOX_AGENT_QUEUE", "/root/nox/state/dispatcher/queue.jsonl")
        self.calendar = e.get("NOX_AGENT_CALENDAR", "") or os.path.join(self.state_dir, "calendar.jsonl")
        self.task_state = e.get("NOX_AGENT_TASK_STATE", "") or os.path.join(self.state_dir, "task_state.jsonl")
        self.reminders = e.get("NOX_AGENT_REMINDERS", "") or os.path.join(self.state_dir, "reminders.jsonl")
        self.reports = e.get("NOX_AGENT_REPORTS", "") or os.path.join(self.state_dir, "reports.jsonl")
        self.skills_db = e.get("NOX_AGENT_SKILLS_DB", "") or os.path.join(self.state_dir, "skills.sqlite3")
        self.code_db = e.get("NOX_AGENT_CODE_DB", "") or os.path.join(self.state_dir, "codeindex.sqlite3")
        self.task_retries = _int(e, "NOX_AGENT_TASK_RETRIES", 2)
        for k, v in kw.items(): setattr(self, k, v)
