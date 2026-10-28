"""NOX Cinema · explicitly authorized, short-lived LAN video gateway for Cast receivers.
One selected, owner-approved local file. Separate from the AI backend. Never auto-started.
The receiving projector fetches bytes directly; no permanent library share, no cloud upload.
"""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
import ipaddress
import os
import re
import secrets
import stat
import time

MAX_BYTES = 40 * 1024**3
EXTENSIONS = {".mp4": "video/mp4", ".webm": "video/webm"}
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 256 * 1024

class MediaHold(RuntimeError):
    pass

def checked_lan_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError as exc:
        raise MediaHold("LAN_IPV4_REQUIRED") from exc
    if (not isinstance(ip, ipaddress.IPv4Address) or not ip.is_private or
        ip.is_loopback or ip.is_link_local or ip.is_multicast or
        ip.is_reserved or ip.is_unspecified):
        raise MediaHold("PRIVATE_LAN_IPV4_REQUIRED")
    return str(ip)

def inspect_local_movie(path: str | Path, *, allowed_root: str | Path) -> tuple[Path, int, str]:
    """Native host must select a local regular movie under its approved library root."""
    src = Path(path).absolute()
    root = Path(allowed_root).absolute()
    if not root.is_dir():
        raise MediaHold("APPROVED_MOVIE_LIBRARY_REQUIRED")
    if src == root or root not in src.parents:
        raise MediaHold("MOVIE_OUTSIDE_APPROVED_LIBRARY")
    cursor = src
    while cursor != root.parent:
        if cursor.is_symlink():
            raise MediaHold("MOVIE_SYMLINK_DENIED")
        if cursor == root:
            break
        cursor = cursor.parent
    try:
        info = src.stat()
    except OSError as exc:
        raise MediaHold("MOVIE_NOT_READABLE") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > MAX_BYTES:
        raise MediaHold("MOVIE_INVALID_SIZE_OR_KIND")
    ext = src.suffix.lower()
    if ext not in EXTENSIONS:
        raise MediaHold("MOVIE_CODEC_NOT_SUPPORTED_FOR_DIRECT_CAST")
    return src, info.st_size, EXTENSIONS[ext]

def parse_range(value: str | None, length: int) -> tuple[int,int,bool]:
    if not value:
        return 0, length - 1, False
    m = RANGE.fullmatch(value.strip())
    if not m or (not m.group(1) and not m.group(2)):
        raise MediaHold("INVALID_BYTE_RANGE")
    left, right = m.groups()
    try:
        if left:
            start = int(left)
            end = int(right) if right else length - 1
        else:
            amount = int(right)
            if amount <= 0:
                raise ValueError
            start = max(0, length - amount)
            end = length - 1
    except ValueError as exc:
        raise MediaHold("INVALID_BYTE_RANGE") from exc
    if start >= length or end < start:
        raise MediaHold("BYTE_RANGE_NOT_SATISFIABLE")
    return start, min(end, length - 1), True

class LocalCastGateway:
    """Reachable only via a user-approved private NIC and a selected private Cast IP.
       No permanent address, user data index, directory traversal or network scanning.
    """
    def __init__(self, file_path: str | Path, *, library_root: str | Path,
                 local_ip: str, device_ip: str, rights_confirmed: bool,
                 ttl_seconds: int = 3600):
        if rights_confirmed is not True:
            raise MediaHold("USER_MOVIE_RIGHTS_REQUIRED")
        self.local_ip = checked_lan_ip(local_ip)
        self.device_ip = checked_lan_ip(device_ip)
        self.path, self.size, self.mime = inspect_local_movie(file_path, allowed_root=library_root)
        if not isinstance(ttl_seconds,int) or not 60 <= ttl_seconds <= 7200:
            raise MediaHold("GATEWAY_TTL_INVALID")
        self.expires = time.monotonic() + ttl_seconds
        self.token = secrets.token_urlsafe(32)
        self._server = None
        self._thread = None
        self.movie_name = "movie" + self.path.suffix.lower()

    def _handler(self):
        gateway = self
        class Handler(BaseHTTPRequestHandler):
            server_version = "NOX-CinemaGateway"
            sys_version = ""
            protocol_version = "HTTP/1.1"
            def log_message(self, _fmt, *_args):
                # Never log access tokens or private file paths.
                return
            def do_HEAD(self):
                self._serve(head_only=True)
            def do_GET(self):
                self._serve(head_only=False)
            def _serve(self, head_only):
                if self.client_address[0] != gateway.device_ip:
                    self.send_error(403, "PROJECTOR_NOT_APPROVED")
                    return
                if time.monotonic() >= gateway.expires:
                    self.send_error(410, "CAST_SESSION_EXPIRED")
                    return
                # Exact path only; query parameters and arbitrary subpaths forbidden.
                if self.path != "/film/" + gateway.token + "/" + gateway.movie_name:
                    self.send_error(404, "UNKNOWN_CAST_SESSION")
                    return
                try:
                    start, end, partial = parse_range(self.headers.get("Range"),gateway.size)
                except MediaHold:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */" + str(gateway.size))
                    self.send_header("Content-Length","0")
                    self.end_headers()
                    return
                size = end - start + 1
                try:
                    # Reject a substituted file while this session is running.
                    if gateway.path.is_symlink() or gateway.path.stat().st_size != gateway.size:
                        self.send_error(409, "MOVIE_CHANGED")
                        return
                    f = gateway.path.open("rb")
                except OSError:
                    self.send_error(404, "MOVIE_UNAVAILABLE")
                    return
                with f:
                    self.send_response(206 if partial else 200)
                    self.send_header("Content-Type", gateway.mime)
                    self.send_header("Content-Length", str(size))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Cache-Control", "no-store, private")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Connection", "close")
                    if partial:
                        self.send_header("Content-Range", "bytes "+str(start)+"-"+str(end)+"/"+str(gateway.size))
                    self.end_headers()
                    if head_only:
                        return
                    f.seek(start)
                    remaining = size
                    try:
                        while remaining > 0:
                            data = f.read(min(CHUNK,remaining))
                            if not data:
                                break
                            self.wfile.write(data)
                            remaining -= len(data)
                    except (ConnectionError, BrokenPipeError, OSError):
                        return
        return Handler

    def start(self) -> str:
        if self._server is not None:
            raise MediaHold("GATEWAY_ALREADY_RUNNING")
        server = ThreadingHTTPServer((self.local_ip, 0), self._handler())
        server.daemon_threads = True
        server.timeout = 2
        self._server = server
        self._thread = Thread(target=server.serve_forever,daemon=True,name="NOX-CastMedia")
        self._thread.start()
        return "http://"+self.local_ip+":"+str(server.server_address[1])+"/film/"+self.token+"/"+self.movie_name

    def stop(self):
        s = self._server
        self._server = None
        if s is not None:
            s.shutdown()
            s.server_close()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
