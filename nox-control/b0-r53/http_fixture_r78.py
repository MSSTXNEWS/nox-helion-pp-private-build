"""R78 loopback HTTP using actual R77 writer, never native authority."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import socket
from b0_http_chunked_r76 import write_chunked_sse

released = threading.Event()
finished = {"/fault": threading.Event(), "/clean": threading.Event()}
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
        if self.path == "/counts":
            if not all(event.wait(10) for event in finished.values()):
                self.send_error(503)
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

        self.close_connection = True

        def headers():
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()

        def abort():
            with lock:
                counts["faults"] += 1
            # Abort the actual connection, never issue a second response.
            self.connection.shutdown(socket.SHUT_RDWR)

        try:
            write_chunked_sse(source(), start_headers=headers,
                              write=self.wfile.write, flush=self.wfile.flush,
                              abort_transport=abort)
            with lock:
                counts["clean"] += 1
        except OSError:
            # The reusable writer owns abort and disposal.
            pass
        finally:
            finished[self.path].set()

if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(server.server_address[1], flush=True)
    server.serve_forever()
