"""Lazy proxy SSE response body for an admitted native delta iterator.

The caller must authenticate the writer and bind the existing exchange
before constructing this adapter; it owns STOP and canonical readback.
The HTTP response owner MUST call close() in its disconnect/finally path,
on the same serialized iterator owner. No model request or ACK here.
"""
from b0_named_delta_encoder import encode_native_delta


class ProxyDeltaBody:
    """Pull one upstream frame per downstream read; no buffering or retry."""
    def __init__(self, upstream):
        if iter(upstream) is not upstream or not callable(getattr(upstream, "close", None)):
            raise TypeError("HOLD_PROXY_CLOSEABLE_NATIVE_ITERATOR_REQUIRED")
        self._upstream = upstream
        self._closed = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._closed:
            raise StopIteration
        try:
            return encode_native_delta(next(self._upstream))
        except BaseException:
            # EOF also closes; a failing close must not become a clean EOF.
            self.close()
            raise

    def close(self):
        """Idempotent disposal, including disconnect before the first pull."""
        if not self._closed:
            self._closed = True
            self._upstream.close()
