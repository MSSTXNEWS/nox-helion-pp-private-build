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
        self._faulted = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._faulted:
            raise RuntimeError("HOLD_PROXY_STREAM_PREVIOUS_FAULT")
        if self._closed:
            raise StopIteration
        try:
            frame = next(self._upstream)
        except StopIteration:
            self.close()
            raise
        except BaseException:
            self._faulted = True
            self.close()
            raise
        try:
            return encode_native_delta(frame)
        except BaseException as exc:
            self._faulted = True
            self.close()
            if isinstance(exc, StopIteration):
                raise RuntimeError("HOLD_PROXY_ENCODER_FALSE_EOF") from exc
            raise

    def close(self):
        """Idempotent disposal, including disconnect before the first pull."""
        if not self._closed:
            self._closed = True
            try:
                self._upstream.close()
            except StopIteration as exc:
                self._faulted = True
                # Disposal failure must never masquerade as a clean stream EOF.
                raise RuntimeError("HOLD_PROXY_CLOSE_FALSE_EOF") from exc
            except BaseException:
                self._faulted = True
                raise
