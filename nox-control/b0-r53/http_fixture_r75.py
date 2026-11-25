"""Loopback HTTP fixture, never a production server or owner provider."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from b0_proxy_stream_iter import ProxyDeltaBody

released = threading.Event()
counts = {"posts": 0, "closed": 0, "faults": 0, "clean": 0}
lock = threading.Lock()

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/release":
            released.set()
        elif self.path != "/counts":
            self.send_error(404)
            return
        with lock:
            raw = json.dumps(counts).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path not in ("/fault", "/clean"):
            self.send_error(404)
            return
        fault = self.path == "/fault"
        with lock:
            counts["posts"] += 1

        def source():
            try:
                yield {"type": "delta", "event_id": "existing:2:1" if fault else "existing:3:1",
                       "text": "Привет 🌞\n¡Hola!" if fault else "  Continuamos\nSí  "}
                if fault:
                    if not released.wait(10):
                        raise TimeoutError("fixture release missing")
                    raise OSError("fixture upstream transport lost")
            finally:
                with lock:
                    counts["closed"] += 1

        body = ProxyDeltaBody(source())
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for chunk in body:
                self.wfile.write(("%x\r\n" % len(chunk)).encode() + chunk + b"\r\n")
                self.wfile.flush()
            # Only a clean iterator exhaustion may finish HTTP chunk framing.
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            with lock:
                counts["clean"] += 1
        except OSError:
            with lock:
                counts["faults"] += 1
            # Do not send final chunk or attempt another model request.
        finally:
            body.close()

if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(server.server_address[1], flush=True)
    server.serve_forever()
