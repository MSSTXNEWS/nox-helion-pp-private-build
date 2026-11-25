"""HTTP/1.1 chunked SSE writer for an already admitted, exclusive route owner.

Only for a raw HTTP/1.1 response whose framing is not managed by another
server layer. start_headers must set chunked SSE headers; abort_transport
must close the underlying connection (not merely end an application body).
No route selection, model POST, retry, terminal ACK or canonical authority.
"""
from b0_proxy_stream_iter import ProxyDeltaBody


def write_chunked_sse(upstream, *, start_headers, write, flush, abort_transport):
    """Own upstream disposal and framing; return only after clean HTTP EOF.

    A write must report its exact byte count. An uncertain/partial write
    aborts rather than retrying. Caller must not generate a fallback response.
    """
    body = ProxyDeltaBody(upstream)
    def emit(data):
        count = write(data)
        if type(count) is not int or count != len(data):
            raise OSError("HOLD_PROXY_HTTP_SHORT_WRITE")
        flush()

    try:
        start_headers()
        for chunk in body:
            emit(("%x\r\n" % len(chunk)).encode("ascii") + chunk + b"\r\n")
        # R74 closes the source successfully before it reports exhaustion.
        emit(b"0\r\n\r\n")
    except BaseException as exc:
        try:
            try:
                abort_transport()
            except StopIteration as abort_exc:
                raise RuntimeError("HOLD_PROXY_HTTP_ABORT_FALSE_EOF") from abort_exc
        finally:
            body.close()
        if isinstance(exc, StopIteration):
            raise RuntimeError("HOLD_PROXY_HTTP_CALLBACK_FALSE_EOF") from exc
        raise
