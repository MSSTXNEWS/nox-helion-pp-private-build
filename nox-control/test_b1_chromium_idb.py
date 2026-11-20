#!/usr/bin/env python3
"""Real Chromium IndexedDB acceptance of B1's opt-in source adapter.

This is a synthetic browser-storage contract check, NOT proof of a deployed
NOX browser, authenticated S03 readback, or end-to-end server resume.
Run from a checked-out repository: python nox-control/test_b1_chromium_idb.py
Requires Python playwright + installed Chromium.
"""
from __future__ import annotations

import os
import tempfile
import threading
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

SOURCE = Path(__file__).resolve().with_name("b1_client_ack_indexeddb_store.js")
HEX_A, HEX_B, HEX_C, HEX_D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)


def packet(exchange="x1", event=HEX_A, proof=HEX_C):
    return {
        "readback_only": True,
        "emit_terminal": True,
        "conversation_id": "b1-browser-dialog",
        "exchange_id": exchange,
        "event_id": event,
        "next_cursor": "signed_synthetic_cursor_b1",
        "response_sha256": HEX_B,
        "s03_proof_sha256": proof,
    }


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS:", label, flush=True)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def attach(page, database):
    page.add_script_tag(path=str(SOURCE))
    page.evaluate(
        """async db => {
            window.b1 = await NOXB1IndexedAckStore.openClientAckHost({
                indexedDB: window.indexedDB,
                databaseName: db,
                authorizeEnvelope: async () => true,
                freshPermit: async () => true
            });
        }""",
        database,
    )


def main():
    assert SOURCE.is_file(), f"Missing exact source under test: {SOURCE}"
    with tempfile.TemporaryDirectory(prefix="nox-b1-browser-") as directory:
        Path(directory, "index.html").write_text(
            "<!doctype html><html><title>NOX B1 IDB test origin</title></html>",
            encoding="utf-8",
        )
        handler = partial(QuietHandler, directory=directory)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{httpd.server_port}/index.html"
        database = f"nox-b1-regression-{uuid.uuid4().hex}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('NOX_B1_CHROME'))
                context = browser.new_context()
                page = context.new_page()
                page.goto(url, wait_until="load")
                attach(page, database)
                result = page.evaluate(
                    """async p => {
                        const other = await NOXB1IndexedAckStore.openClientAckHost({
                            indexedDB, databaseName: window.b1DbName,
                            authorizeEnvelope: async () => true,
                            freshPermit: async () => true
                        });
                        try {
                            return await Promise.all([
                                window.b1.commitTerminalAndAck(p),
                                other.commitTerminalAndAck(p)
                            ]);
                        } finally {other.close();}
                    }""".replace("window.b1DbName", repr(database)),
                    packet(),
                )
                check(
                    "two real IndexedDB connections serialize duplicate ACK",
                    sorted(result) == ["ALREADY_COMMITTED", "COMMITTED"],
                )
                check(
                    "second real transaction accepts a distinct exchange",
                    page.evaluate(
                        "p => window.b1.commitTerminalAndAck(p)",
                        packet("x2", HEX_D),
                    ) == "COMMITTED",
                )
                check(
                    "lost ACK retry is readonly/idempotent, not a third turn",
                    page.evaluate(
                        "p => window.b1.commitTerminalAndAck(p)",
                        packet(),
                    ) == "ALREADY_COMMITTED",
                )
                conflict = page.evaluate(
                    """async p => {
                        try { await b1.commitTerminalAndAck(p); return "BAD"; }
                        catch (e) { return e.code; }
                    }""",
                    packet(proof=HEX_D),
                )
                check("different S03 proof on same exchange fails closed", conflict == "HOLD_ACK_CONFLICT")
                collision = page.evaluate(
                    """async p => {
                        try { await b1.commitTerminalAndAck(p); return "BAD"; }
                        catch (e) { return e.code; }
                    }""",
                    packet("x3", HEX_A),
                )
                check("event_id collision across turns fails closed", collision == "HOLD_ACK_EVENT_COLLISION")
                page.evaluate("() => b1.close()")
                page.close()
                reopened = context.new_page()
                reopened.goto(url, wait_until="load")
                attach(reopened, database)
                persisted = reopened.evaluate(
                    """async () => Promise.all([
                        b1.readCommitted("b1-browser-dialog", "x1"),
                        b1.readCommitted("b1-browser-dialog", "x2"),
                        b1.readCommitted("b1-browser-dialog", "x3")
                    ])"""
                )
                check(
                    "fresh Chromium page reload sees two durable unique turns, no x3",
                    persisted[0]["event_id"] == HEX_A
                    and persisted[1]["event_id"] == HEX_D
                    and persisted[0]["durable"] is True
                    and persisted[1]["durable"] is True
                    and persisted[2] is None,
                )
                check(
                    "reopened browser connection cannot duplicate terminal",
                    reopened.evaluate("p => b1.commitTerminalAndAck(p)", packet())
                    == "ALREADY_COMMITTED",
                )
                reopened.evaluate("() => b1.close()")
                context.close()
                browser.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    main()
