"""Real Chromium and WEB assets with a local HTTP contract fixture. No GPU or OneHost."""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import Event, Thread
from urllib.parse import urlsplit
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

DIALOG = "d" * 32
JOB = "e" * 32
ANSWER = "Ответ 👩‍💻 / gracias"
WEB = "/nox-web-v29/pc/resonance.html"


class Turn:
    def __init__(self):
        self.received = Event()
        self.prepare = Event()
        self.delta = Event()
        self.done = Event()

    def release(self):
        for gate in (self.prepare, self.delta, self.done):
            gate.set()


class SiteFixture:
    def __init__(self):
        self.turns = {name: Turn() for name in (
            "принятие и сохранение", "остановить это", "сохранить соседний", "текст пока рисуется",
        )}
        self.calls = []
        self.history = []


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, fixture, **kwargs):
        self.fixture = fixture
        super().__init__(*args, **kwargs)

    def log_message(self, *args):
        pass

    def write_json(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/nox/status":
            self.write_json({"model": "LOCAL CONTRACT FIXTURE", "model_label": "LOCAL FIXTURE"})
        elif path == "/api/ui/memory/dialogs":
            self.write_json({"status": "READY", "dialogs": [{"dialog_id": DIALOG, "title": "Локальный тест"}]})
        elif path == "/api/ui/memory/dialogs/history":
            self.write_json({"status": "READY", "dialog_id": DIALOG, "messages": self.fixture.history})
        elif path == "/api/ui/media":
            self.write_json({"image": True, "video": False})
        elif path == "/api/ui/media/jobs/" + JOB:
            self.write_json({"id": JOB, "kind": "image", "state": "QUEUED", "outputs": []})
        elif path.startswith("/api/"):
            self.write_json({})
        else:
            self.path = self.path.removeprefix("/nox-web-v29")
            super().do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        self.fixture.calls.append((path, data))
        if path == "/api/ui/media/jobs":
            self.write_json({"id": JOB, "kind": "image", "state": "QUEUED"})
        elif path == "/api/nox/chat/stream":
            self.stream_turn(data)
        elif path == "/api/ui/memory/dialogs/create":
            self.write_json({"dialog_id": DIALOG})
        else:
            self.write_json({"error": "UNEXPECTED_FIXTURE_REQUEST"}, 404)

    def stream_turn(self, data):
        prompt = data["message"]
        turn = self.fixture.turns[prompt]
        turn.received.set()
        exchange = data["request_id"] + "-s03"
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()

        def frame(value):
            self.wfile.write(json.dumps(value, ensure_ascii=False).encode() + b"\n")
            self.wfile.flush()

        try:
            if not turn.prepare.wait(12):
                return
            frame({"type": "preparing", "stream_mode": "NATIVE_TOKEN_STREAM"})
            frame({"type": "start", "model": "LOCAL CONTRACT FIXTURE"})
            if not turn.delta.wait(12):
                return
            frame({"type": "delta", "text": ANSWER})
            if not turn.done.wait(12):
                return
            self.fixture.history.extend([
                {"role": "user", "content": prompt, "exchange_id": exchange},
                {"role": "assistant", "content": ANSWER, "exchange_id": exchange},
            ])
            frame({"type": "done", "saved": True, "s03_integrated": True, "dialog_id": DIALOG, "exchange_id": exchange})
        except (BrokenPipeError, ConnectionResetError):
            pass


def run(source: Path, overlays: Path, chromium: Path | None):
    with TemporaryDirectory() as tmp:
        site = Path(tmp) / "site"
        with ZipFile(source) as archive:
            for member in archive.namelist():
                if member.startswith("site/"):
                    archive.extract(member, tmp)
        for file in (overlays / "site").rglob("*.js"):
            shutil.copyfile(file, site / file.relative_to(overlays / "site"))
        fixture = SiteFixture()
        with ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=site, fixture=fixture)) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with sync_playwright() as playwright:
                    flags = ["--no-sandbox"]
                    if chromium:
                        flags += ["--no-zygote", "--single-process", "--use-angle=swiftshader",
                                  "--use-gl=angle", "--disable-dev-shm-usage"]
                    browser = playwright.chromium.launch(
                        executable_path=chromium or shutil.which("chromium"), args=flags,
                    )
                    context = browser.new_context(reduced_motion="reduce")
                    context.add_init_script("window.NOX_NATIVE_OWNER = true")
                    url = f"http://127.0.0.1:{server.server_address[1]}" + WEB

                    def tab():
                        current = context.new_page()
                        current.goto(url, wait_until="domcontentloaded")
                        expect(current.locator("body")).to_have_attribute("data-v24-ready", "true")
                        return current

                    def submit(page, prompt):
                        page.locator("#prompt").fill(prompt)
                        page.locator("#prompt").press("Enter")
                        turn = fixture.turns[prompt]
                        assert turn.received.wait(8), f"no native fixture request for {prompt}"
                        return turn

                    page = tab()
                    turn = submit(page, "принятие и сохранение")
                    user = page.locator(".v24-msg.me").last
                    bot = page.locator(".v24-msg.nox").last
                    expect(user.locator(".meta")).to_have_text("Отправляется…")
                    turn.prepare.set()
                    expect(user.locator(".meta")).to_have_text("Принято · ожидаю ответ")
                    turn.delta.set()
                    expect(bot.locator(".body")).to_contain_text("Ответ 👩‍💻")
                    expect(user.locator(".meta")).to_have_text("Принято · ожидаю ответ")
                    turn.done.set()
                    expect(user.locator(".meta")).to_have_text("Сохранено в S03")
                    assert user.get_attribute("data-exchange-id") == bot.get_attribute("data-exchange-id")
                    assert bot.get_attribute("data-exchange-id")
                    page.reload(wait_until="domcontentloaded")
                    expect(page.locator(".v24-msg.nox").last.locator(".body")).to_have_text(ANSWER)
                    print("PASS Chromium: pending -> accepted -> real chunk -> verified matching history -> reload")

                    other = tab()
                    first = submit(page, "остановить это")
                    second = submit(other, "сохранить соседний")
                    first.prepare.set()
                    second.prepare.set()
                    expect(page.locator(".v24-msg.me").last.locator(".meta")).to_have_text("Принято · ожидаю ответ")
                    expect(other.locator(".v24-msg.me").last.locator(".meta")).to_have_text("Принято · ожидаю ответ")
                    page.locator('[data-action="stop"]').click()
                    expect(page.locator(".v24-msg.nox").last.locator(".meta")).to_have_text("остановлено STOP")
                    expect(page.locator(".v24-msg.me").last.locator(".meta")).to_have_text("Сохранение не подтверждено")
                    assert not any(path == "/api/nox/stop" for path, _ in fixture.calls)
                    second.release()
                    expect(other.locator(".v24-msg.me").last.locator(".meta")).to_have_text("Сохранено в S03")
                    print("PASS Chromium: STOP this tab, neighboring request survives, no legacy STOP")

                    page.locator("#prompt").fill("/photo теплое солнце")
                    page.locator("#prompt").press("Enter")
                    expect(page.locator(".nox-media-status")).to_contain_text("В очереди")
                    assert any(path == "/api/ui/media/jobs" and data["prompt"] == "теплое солнце" for path, data in fixture.calls)
                    assert not any(path == "/api/nox/chat/stream" and data["message"].startswith("/photo") for path, data in fixture.calls)
                    submit(page, "текст пока рисуется").release()
                    expect(page.locator(".v24-msg.me").last.locator(".meta")).to_have_text("Сохранено в S03")
                    expect(page.locator(".nox-media-status")).to_contain_text("В очереди")
                    print("PASS Chromium: Enter dispatches to media queue, text still runs while media is queued")
                    browser.close()
            finally:
                # Unblock the cancelled mock HTTP thread without manufacturing a save.
                server.shutdown()
                worker.join(timeout=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("overlays", type=Path)
    parser.add_argument("--chromium", type=Path)
    args = parser.parse_args()
    run(args.source, args.overlays, args.chromium)
