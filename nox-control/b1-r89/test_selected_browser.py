"""Exact A3 selected R88 browser bytes; fixture authority only."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Thread
import hashlib, subprocess, tempfile, json, os
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
PIN="37a756fdc6544f8b5d73425c83221bb958504bd3199dd6245aa4d4b62549651f"
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<!doctype html><meta charset=utf-8><main id=chat></main>")
    def log_message(self,*args): pass
with tempfile.TemporaryDirectory() as tmp:
    staged=Path(tmp)/"selected.js"
    subprocess.run(["node",str(ROOT/"b1-r88/stage_r100.cjs"),str(ROOT/"b1-r86/b1_browser_bundle.js"),str(staged)],check=True)
    assert hashlib.sha256(staged.read_bytes()).hexdigest()==PIN
    assert staged.stat().st_size==89135
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            args={"headless":True}
            if os.environ.get("B1_CHROMIUM"): args["executable_path"]=os.environ["B1_CHROMIUM"]
            browser=p.chromium.launch(**args)
            page=browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.add_script_tag(path=str(staged))
            result=page.evaluate((Path(__file__).parent/"exercise.cjs").read_text())
            assert result["count"]==32 and result["rows"]==2
            assert sum(x["acks"] for x in result["results"])==2
            print("B1_R89_BROWSER",json.dumps(result,ensure_ascii=False),flush=True)
            browser.close()
    finally: server.shutdown()
