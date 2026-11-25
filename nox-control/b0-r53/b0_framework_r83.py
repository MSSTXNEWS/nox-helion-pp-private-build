"""R83 framework-only constructor fence; no native authority or retry."""
from b0_framework_r80 import FrameworkDeltaBody as R80Body


class FrameworkDeltaBody(R80Body):
    """Dispose a supplied source when R80 construction fails, never emit EOF."""
    def __init__(self, upstream):
        try:
            super().__init__(upstream)
        except BaseException as exc:
            # R74 construction has not taken ownership on failure.
            try:
                close = getattr(upstream, "close", None)
                if callable(close):
                    close()
            except StopIteration as close_exc:
                raise RuntimeError("HOLD_PROXY_FRAMEWORK_INIT_CLOSE_FALSE_EOF") from close_exc
            if isinstance(exc, StopIteration):
                raise RuntimeError("HOLD_PROXY_FRAMEWORK_INIT_FALSE_EOF") from exc
            raise
