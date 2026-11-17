"""Bounded subprocess/HTTPS transports. No shell, URL input or raw error logs."""
import http.client
import json
import os
import selectors
import signal
import ssl
import subprocess
import time


class BridgeError(Exception):
    def __init__(self, code, *, outcome_uncertain=False, http_status=None):
        super().__init__(code)
        self.code = code
        self.outcome_uncertain = outcome_uncertain
        self.http_status = http_status

    def public(self):
        result = {"status": "blocked", "code": self.code, "outcome_uncertain": self.outcome_uncertain}
        if self.http_status is not None:
            result["http_status"] = self.http_status
        return result


class BoundedRunner:
    """Linux process scope with bounded stdout, stderr and wall time."""
    def run(self, argv, *, env, timeout, max_output, sink=None, should_pause=None):
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) for x in argv):
            raise BridgeError("INVALID_ARGV")
        if should_pause is not None and should_pause():
            raise BridgeError("CANCELLED")
        try:
            p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, shell=False, env=env,
                                 start_new_session=True, close_fds=True)
        except OSError:
            raise BridgeError("COMMAND_START_FAILED") from None
        collected = bytearray()
        stdout_bytes = stderr_bytes = 0
        deadline = time.monotonic() + timeout
        selector = selectors.DefaultSelector()
        try:
            for pipe, label in ((p.stdout, "out"), (p.stderr, "err")):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, label)
            while selector.get_map():
                if should_pause is not None and should_pause():
                    raise BridgeError("CANCELLED")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BridgeError("COMMAND_TIMEOUT")
                for key, _ in selector.select(min(0.1, remaining)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "err":
                        stderr_bytes += len(chunk)
                        if stderr_bytes > 65536:
                            raise BridgeError("COMMAND_STDERR_LIMIT")
                        continue  # Never return rclone stderr: it may contain credentials.
                    stdout_bytes += len(chunk)
                    if stdout_bytes > max_output:
                        raise BridgeError("COMMAND_OUTPUT_LIMIT")
                    if sink is None:
                        collected.extend(chunk)
                    else:
                        sink.write(chunk)
            if p.wait(timeout=max(0.01, deadline-time.monotonic())) != 0:
                raise BridgeError("COMMAND_FAILED")
            return bytes(collected)
        except subprocess.TimeoutExpired:
            raise BridgeError("COMMAND_TIMEOUT") from None
        finally:
            selector.close()
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait(timeout=5)
            p.stdout.close()
            p.stderr.close()


OFFICIAL_HOSTS = frozenset({"api.notion.com", "api.github.com", "gitlab.com"})


class HTTPSJSON:
    """Fixed official hosts; redirects, proxies and arbitrary endpoints absent."""
    def __init__(self, *, timeout=12, max_bytes=1024*1024, connection_factory=None):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.connection_factory = connection_factory

    def request(self, host, method, path, headers, body=None):
        if host not in OFFICIAL_HOSTS or method not in ("GET", "POST"):
            raise BridgeError("TRANSPORT_NOT_ALLOWED")
        if not path.startswith("/") or path.startswith("//") or any(ord(c)<32 for c in path) or "#" in path:
            raise BridgeError("INVALID_API_PATH")
        if any("\r" in k+v or "\n" in k+v for k,v in headers.items()):
            raise BridgeError("INVALID_HTTP_HEADER")
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        if payload is not None and len(payload) > 16384:
            raise BridgeError("API_PAYLOAD_LIMIT")
        hdr = {"Accept":"application/json", "User-Agent":"NOX-OneHost-Integrations/0.1", **headers}
        if payload is not None:
            hdr["Content-Type"] = "application/json"
        factory = self.connection_factory or (lambda h,t: http.client.HTTPSConnection(h, timeout=t, context=ssl.create_default_context()))
        conn = factory(host, self.timeout)
        deadline = time.monotonic() + self.timeout
        response = None
        try:
            conn.request(method, path, body=payload, headers=hdr)
            response = conn.getresponse()
            status = response.status
            if status != 200:
                code = "REDIRECT_REJECTED" if 300 <= status < 400 else "RATE_LIMITED" if status == 429 else "API_HTTP_ERROR"
                raise BridgeError(code, http_status=status)
            length = response.getheader("Content-Length")
            if length is not None and (not length.isdigit() or int(length)>self.max_bytes):
                raise BridgeError("API_RESPONSE_LIMIT")
            buf=bytearray()
            while True:
                remaining=deadline-time.monotonic()
                if remaining <= 0:
                    raise BridgeError("API_TIMEOUT")
                sock = getattr(conn, "sock", None)
                if sock is None:
                    sock=getattr(getattr(getattr(response,"fp",None),"raw",None),"_sock",None)
                if sock is not None:
                    sock.settimeout(remaining)
                chunk=response.read1(min(65536,self.max_bytes+1-len(buf)))
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf)>self.max_bytes:
                    raise BridgeError("API_RESPONSE_LIMIT")
            if length is not None and len(buf)!=int(length):
                raise BridgeError("API_RESPONSE_TRUNCATED")
            try:
                value=json.loads(buf)
            except (ValueError,UnicodeError):
                raise BridgeError("API_INVALID_JSON") from None
            if not isinstance(value,dict):
                raise BridgeError("API_INVALID_SHAPE")
            return value
        except (OSError, http.client.HTTPException):
            raise BridgeError("API_TRANSPORT_ERROR") from None
        finally:
            if response is not None:
                response.close()
            conn.close()
