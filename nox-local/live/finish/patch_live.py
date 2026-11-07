"""Patch only the pinned original NOX LIVE payload, never a second backend.

Source baseline is nox-local/live/NOX_LIVE_PAYLOAD.json (26 original files).
Patches: bounded real Ollama stream error/STOP and one terminal DONE receipt,
client rejection of truncated NDJSON, on-device-only RU/ES voice widget.
The outputs are staged files, not modifications to owner weights or SQLite.
"""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path

REQUIRED = {
    "server_live.py": "3549030B2BCD994CA2427521375332F04C9FA7159F5A6B5733AFEF7888821715",
    "chat-live.js": "C829612AC1F4B847FDAD1BBFFE85D31191B524DB434C624BBAB5772C43D2D0EC",
    "chat.html": "CE2BB54E00D5799A09B69EBBC5DA837062EB8F6957BAECAE898066B0C5E94325",
}

def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest().upper()

def replace_exact(text: str, before: str, after: str, label: str) -> str:
    if text.count(before) != 1:
        raise RuntimeError(f"NOX_PAYLOAD_PREIMAGE_HOLD:{label}:{text.count(before)}")
    return text.replace(before, after, 1)

def read_original(payload: Path) -> dict[str, bytes]:
    manifest = json.loads(payload.read_text(encoding="utf-8"))
    if manifest.get("schema") != "NOX_SOURCE_PAYLOAD_V1" or len(manifest.get("files", [])) != 26:
        raise RuntimeError("NOX_PAYLOAD_SCHEMA_OR_COUNT_HOLD")
    out = {}
    for f in manifest["files"]:
        name = f["name"]
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or "\\" in name or
                name.startswith(("/", ".")) or ":" in name or name in out):
            raise RuntimeError("NOX_PAYLOAD_PATH_HOLD:" + name)
        blob = base64.b64decode(f["base64"], validate=True)
        if sha256(blob) != f["sha256"].upper() or len(blob) != f["bytes"]:
            raise RuntimeError("NOX_PAYLOAD_BYTES_SHA_HOLD:" + name)
        out[name] = blob
    for name, expected in REQUIRED.items():
        if sha256(out[name]) != expected:
            raise RuntimeError("NOX_PAYLOAD_ORIGINAL_PREIMAGE_HOLD:" + name)
    return out

NEW_CHAT_STREAM = '''
    def _chat_stream(self):
        # Owner-bound, actual localhost Ollama NDJSON. No fake completion on EOF.
        item = None
        request_id = None
        headers_started = False
        terminal = False
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 2 or length > 65000:
                return self._json(400, {'error': 'invalid message length'})
            data = json.loads(self.rfile.read(length))
            request_id = data.get('request_id')
            if not isinstance(request_id, str) or not 8 <= len(request_id) <= 80:
                return self._json(400, {'error': 'request_id required'})
            model = data.get('model')
            history = data.get('messages')
            if not isinstance(model, str) or model not in {
                m.get('name') for m in base.models()
            }:
                return self._json(400, {'error': 'model unavailable'})
            if not isinstance(history, list) or not 0 < len(history) <= 60:
                return self._json(400, {'error': 'invalid history'})
            if any(
                not isinstance(m, dict) or
                m.get('role') not in ('system', 'user', 'assistant') or
                not isinstance(m.get('content'), str) or
                len(m['content']) > 10000 for m in history
            ):
                return self._json(400, {'error': 'invalid message'})
            with ACTIVE_LOCK:
                if request_id in ACTIVE:
                    return self._json(409, {'error': 'duplicate request id'})
                if len(ACTIVE) >= 2:
                    return self._json(429, {'error': 'NOX_CHAT_BUSY_HOLD'})
                item = {'stop': threading.Event(), 'upstream': None}
                ACTIVE[request_id] = item
            payload = json.dumps({
                'model': model, 'messages': history, 'stream': True,
                'think': False, 'options': {'num_ctx': 4096, 'num_predict': 1024}
            }, ensure_ascii=False).encode('utf-8')
            upstream_request = netreq.Request(
                base.OLLAMA + '/api/chat', data=payload,
                headers={'Content-Type': 'application/json'}, method='POST')
            with netreq.urlopen(upstream_request, timeout=45) as upstream:
                with ACTIVE_LOCK:
                    item['upstream'] = upstream
                if item['stop'].is_set():
                    return self._json(409, {'error': 'NOX_CHAT_CANCELLED_BEFORE_START'})
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Accel-Buffering', 'no')
                self.end_headers()
                headers_started = True
                self.close_connection = True
                while not item['stop'].is_set():
                    line = upstream.readline(262144)
                    if not line:
                        break
                    if len(line) >= 262144 and not line.endswith(b'\\n'):
                        raise ValueError('NOX_NDJSON_LINE_TOO_LARGE_HOLD')
                    if item['stop'].is_set():
                        break
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError) as exc:
                        raise ValueError('NOX_NDJSON_MALFORMED_HOLD') from exc
                    if not isinstance(event, dict):
                        raise ValueError('NOX_NDJSON_EVENT_HOLD')
                    self.wfile.write(line)
                    self.wfile.flush()
                    if event.get('done') is True:
                        terminal = True
                        break
                if not item['stop'].is_set() and not terminal:
                    self.wfile.write(b'{"error":"NOX_STREAM_INCOMPLETE_HOLD","done":true}\\n')
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            if item is not None and item['stop'].is_set():
                return
            if headers_started:
                try:
                    event = json.dumps({
                        'error': 'NOX_LOCAL_OLLAMA_STREAM_HOLD:' + type(error).__name__,
                        'done': True
                    }, ensure_ascii=False).encode('utf-8') + b'\\n'
                    self.wfile.write(event)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
            else:
                try:
                    self._json(502, {'error': 'NOX_LOCAL_OLLAMA_UNAVAILABLE_HOLD'})
                except (BrokenPipeError, ConnectionResetError):
                    pass
        finally:
            if item is not None and request_id is not None:
                with ACTIVE_LOCK:
                    if ACTIVE.get(request_id) is item:
                        ACTIVE.pop(request_id, None)
'''
def patch_source(files: dict[str, bytes], voice_path: Path) -> dict[str, bytes]:
    server = files["server_live.py"].decode("utf-8-sig")
    server = replace_exact(
        server,
        "if not isinstance(rid,str) or len(rid)>80",
        "if not isinstance(rid,str) or not 8<=len(rid)<=80",
        "STOP_REQUEST_ID")
    old_start = server.index("    def _chat_stream(self):")
    old_end = server.index("if __name__=='__main__':", old_start)
    server = server[:old_start] + NEW_CHAT_STREAM + server[old_end:]
    # Ordinary NOX LIVE health is not an assertion of functioning GPU/S03.
    server = replace_exact(
        server, "'scope':'read-only adapters'",
        "'scope':'read-only adapters','identity':'NOX_LOCAL_LIVE_V1','releaseAccepted':False",
        "LOCAL_WEB_IDENTITY")
    files["server_live.py"] = server.encode("utf-8")
    client = files["chat-live.js"].decode("utf-8-sig")
    client = replace_exact(client,
        "let buffer='',answer='';while(true)",
        "let buffer='',answer='',completed=false;while(true)",
        "CHAT_TERMINAL_STATE")
    client = replace_exact(client,
        "if(data.error)throw new Error(data.error);const token=data.message?.content;",
        "if(data.error)throw new Error(data.error);if(data.done===true)completed=true;const token=data.message?.content;",
        "CHAT_TERMINAL_RECEIPT")
    client = replace_exact(client,
        "}if(!answer){out.textContent='Модель не вернула текст';return}",
        "}if(!completed)throw new Error('NOX_STREAM_INCOMPLETE_HOLD');if(!answer){out.textContent='Модель не вернула текст';return}",
        "CHAT_FAIL_CLOSED_EOF")
    files["chat-live.js"] = client.encode("utf-8")
    page = files["chat.html"].decode("utf-8-sig")
    page = replace_exact(page,
        '<script src="./chat-live.js"></script>',
        '<script src="./chat-live.js"></script><script src="./voice-live.js" defer></script>',
        "VOICE_SCRIPT")
    files["chat.html"] = page.encode("utf-8")
    voice = voice_path.read_bytes()
    if b'NOX_VOICE_LOCAL_ONLY_V1' not in voice:
        raise RuntimeError("VOICE_SOURCE_ID_MISMATCH_HOLD")
    files["voice-live.js"] = voice
    return files

if __name__ == "__main__":
    import argparse
    a = argparse.ArgumentParser()
    a.add_argument("--payload", type=Path, required=True)
    a.add_argument("--voice", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    args = a.parse_args()
    files = patch_source(read_original(args.payload), args.voice)
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit("OUT_NOT_EMPTY_HOLD")
    args.out.mkdir(parents=True, exist_ok=True)
    for name, blob in files.items():
        target = args.out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    manifest = {"schema":"NOX_WEB_11_22_STAGED_V1",
                "instructions_version":"0.0.6",
                "scope":"existing NOX LIVE, source-only, no user weights/SQLite",
                "files":[{"name":n,"bytes":len(b),"sha256":sha256(b)} for n,b in sorted(files.items())]}
    (args.out/"NOX_WEB_STAGED_MANIFEST.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print("NOX_WEB_STAGE_SOURCE_PASS", len(files), "files")
