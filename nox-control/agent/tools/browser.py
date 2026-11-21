"""browser: Playwright (sync API), если установлен; иначе честная ошибка. Те же URL-проверки и прокси, что у fetch_page."""
from . import Tool, err
from . import web

NEED = "pip install playwright && python3 -m playwright install chromium"


def _pw():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright, None
    except Exception as e:
        return None, e


def tool_browser(a, ctx):
    cfg = ctx.cfg
    sp, e = _pw()
    if sp is None:
        return err("Playwright не установлен", blocked=True, need=NEED)
    lim = web._limit(ctx)
    if lim: return lim
    bad = web.check_url(a["url"], cfg)
    if bad: return err(bad)
    act = a.get("action", "text")
    try:
        with sp() as p:
            kw = {"headless": True}
            if cfg.proxy: kw["proxy"] = {"server": cfg.proxy}
            try:
                br = p.chromium.launch(**kw)
            except Exception as e2:
                return err("браузер не запускается: %s" % str(e2).splitlines()[0][:200], blocked=True, need=NEED)
            try:
                pg = br.new_page()
                pg.set_default_timeout(int(cfg.web_timeout * 1000))
                pg.route("**/*", lambda route: route.abort() if web.check_url(route.request.url, cfg) and route.request.url.startswith(("http", "ws")) else route.continue_())
                pg.goto(a["url"])
                if a.get("click"): pg.click(a["click"])
                if a.get("fill") and a.get("selector"): pg.fill(a["selector"], a["fill"])
                if act == "screenshot":
                    import os, tempfile
                    path = os.path.join(tempfile.gettempdir(), "nox-agent-shot-%d.png" % ctx.bump("shot"))
                    pg.screenshot(path=path)
                    return {"ok": True, "path": path, "url": pg.url, "title": pg.title()}
                c = web.clean_html(pg.content())
                return {"ok": True, "url": pg.url, "title": c["title"], "text": c["text"][:cfg.web_max_chars], "untrusted": True}
            finally:
                br.close()
    except Exception as e3:
        return err("браузер: %s" % str(e3).splitlines()[0][:300])


TOOLS = [Tool("browser", "Открыть страницу в headless-браузере (Playwright) для JS-сайтов: text или screenshot; необязательно click/fill. Если Playwright не установлен, вернёт ошибку.",
              {"type": "object", "properties": {"url": {"type": "string"}, "action": {"type": "string", "enum": ["text", "screenshot"]}, "click": {"type": "string"},
                                                "selector": {"type": "string"}, "fill": {"type": "string"}}, "required": ["url"]}, tool_browser)]
