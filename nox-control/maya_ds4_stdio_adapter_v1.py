"""Narrow Maya DS4 --serve stdin/stdout framing adapter.

This is a token-ID transport primitive, not an OpenAI chat provider.  It is
disabled by default and is not wired to the NOX bridge.  NOX still needs an
approved in-process tokenizer/chat-template path before this can consume chat
messages.
"""
from __future__ import annotations

import subprocess
import threading
from typing import Callable, Iterable, Iterator, Sequence


class MayaAdapterHold(RuntimeError):
    pass


class MayaProtocolError(RuntimeError):
    pass


class MayaStdioAdapter:
    """One-request-at-a-time transport for a Maya `--serve` process.

    `argv` is the already reviewed Maya invocation, excluding no framing
    assumptions. `enabled=False` prevents even process creation.
    """

    def __init__(self, argv: Sequence[str], *, enabled: bool = False,
                 popen: Callable = subprocess.Popen):
        self.argv = tuple(argv)
        self.enabled = enabled
        self._popen = popen
        self._proc = None
        self._lock = threading.Lock()
        self._ready = False
        self.gpu_stop_verified = False

    @property
    def state(self) -> str:
        if not self.enabled:
            return "HOLD_MAYA_BINARY_EXECUTED_FALSE"
        return "PROCESS_READY" if self._ready else "HOLD_PROCESS_NOT_READY"

    def start(self) -> None:
        if not self.enabled:
            raise MayaAdapterHold("MAYA_BINARY_EXECUTED=false; adapter is disabled")
        if self._proc is not None:
            return
        if not self.argv:
            raise MayaAdapterHold("HOLD_MAYA_ARGV_EMPTY")
        self._proc = self._popen(list(self.argv), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, encoding="utf-8", bufsize=1)
        while True:
            line = self._readline()
            if not line:
                raise MayaProtocolError("engine exited before READY")
            if line.startswith(("INFO ", "VRAM ", "NOTE ")):
                continue
            fields = line.split()
            if fields and fields[0] == "READY" and len(fields) >= 2:
                if "stop" not in fields[2:]:
                    raise MayaAdapterHold("HOLD_ENGINE_STOP_UNSUPPORTED")
                if any(part.startswith("multi=") for part in fields[2:]):
                    raise MayaAdapterHold("HOLD_MULTI_PROTOCOL_UNSUPPORTED")
                self._ready = True
                return
            raise MayaProtocolError(f"unexpected startup frame: {line.rstrip()}")

    def _readline(self) -> str:
        assert self._proc is not None and self._proc.stdout is not None
        return self._proc.stdout.readline()

    def generate_ids(self, token_ids: Iterable[int], max_new: int) -> Iterator[int]:
        """Yield `T <id>` values. Closing early sends STOP and drains through DONE."""
        if not self.enabled:
            raise MayaAdapterHold("MAYA_BINARY_EXECUTED=false; adapter is disabled")
        ids = tuple(int(t) for t in token_ids)
        if not ids or max_new <= 0:
            raise ValueError("token_ids and positive max_new are required")

        def stream() -> Iterator[int]:
            with self._lock:
                self.start()
                assert self._proc is not None and self._proc.stdin is not None
                self._proc.stdin.write(f"GEN {int(max_new)} " + ",".join(map(str, ids)) + "\n")
                self._proc.stdin.flush()
                ended = False
                try:
                    while True:
                        line = self._readline()
                        if not line:
                            raise MayaProtocolError("engine exited during generation")
                        if line.startswith("T "):
                            fields = line.split()
                            if len(fields) != 2 or not fields[1].isdigit():
                                raise MayaProtocolError(f"malformed token frame: {line.rstrip()}")
                            yield int(fields[1])
                        elif line.startswith("DONE "):
                            ended = True
                            return
                        elif line.startswith("ERR "):
                            ended = True
                            raise MayaProtocolError(line[4:].strip())
                        elif line.startswith(("STAT ", "PP ", "NOTE ")):
                            continue
                        else:
                            raise MayaProtocolError(f"unexpected generation frame: {line.rstrip()}")
                finally:
                    if not ended:
                        self._proc.stdin.write("STOP\n")
                        self._proc.stdin.flush()
                        while True:
                            line = self._readline()
                            if not line:
                                break
                            if line.startswith("DONE ") or line.startswith("ERR "):
                                break
        return stream()

    def close(self) -> None:
        proc, self._proc = self._proc, None
        self._ready = False
        if proc is None:
            return
        if proc.stdin is not None:
            try:
                proc.stdin.write("QUIT\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)

