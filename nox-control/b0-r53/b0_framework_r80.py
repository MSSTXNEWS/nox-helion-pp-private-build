"""Framework-framed response adapter. No manual HTTP chunks, retry or ACK.
Only an already admitted, serialized route owner may use this adapter.
A clean drain is transport EOF only, never terminal/canonical authority.
"""
from b0_proxy_stream_iter import ProxyDeltaBody


class FrameworkDeltaBody:
    def __init__(self, upstream):
        self._body = ProxyDeltaBody(upstream)
        self._state = "OPEN"

    def __iter__(self):
        return self

    def __next__(self):
        if self._state == "DRAINED":
            raise StopIteration
        if self._state != "OPEN":
            raise RuntimeError("HOLD_PROXY_FRAMEWORK_" + self._state)
        try:
            return next(self._body)
        except StopIteration:
            self._state = "DRAINED"
            raise
        except BaseException:
            self._state = "FAULT"
            raise

    def close(self):
        """Serialized disconnect/finally. Never promote cancellation to drain."""
        if self._state == "OPEN":
            self._state = "CANCELLED"
        try:
            self._body.close()
        except BaseException:
            self._state = "FAULT"
            raise
