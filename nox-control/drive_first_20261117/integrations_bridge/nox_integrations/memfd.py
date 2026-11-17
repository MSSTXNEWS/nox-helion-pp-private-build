"""Owned RAM artifact handle. The persistent host controls its loader lifetime."""
import os
import fcntl

from .core import BridgeError

RAM_TRANSPORT_OVERHEAD=64*1024*1024
# Linux UAPI include/uapi/linux/fcntl.h. Some Python builds omit these symbols
# although the running Linux kernel supports seals; numeric values are stable.
F_ADD_SEALS=getattr(fcntl,"F_ADD_SEALS",1033)
F_GET_SEALS=getattr(fcntl,"F_GET_SEALS",1034)
REQUIRED_SEALS=(getattr(fcntl,"F_SEAL_WRITE",8)|getattr(fcntl,"F_SEAL_GROW",4)
                |getattr(fcntl,"F_SEAL_SHRINK",2)|getattr(fcntl,"F_SEAL_SEAL",1))


class MemfdHandle:
    def __init__(self,fd,*,size_bytes,sha256,lease,release_ram):
        self._fd=fd
        s=os.fstat(fd)
        self._identity=(s.st_dev,s.st_ino)
        self.size_bytes=size_bytes
        self.sha256=sha256
        self._lease=lease
        self._release_ram=release_ram
        self.closed=False

    def __repr__(self):
        return f"MemfdHandle(size_bytes={self.size_bytes}, sealed=True, closed={self.closed})"

    def fileno(self):
        if self.closed:
            raise BridgeError("RAM_HANDLE_CLOSED")
        try:
            s=os.fstat(self._fd)
        except OSError:
            raise BridgeError("RAM_HANDLE_UNAVAILABLE") from None
        if (s.st_dev,s.st_ino)!=self._identity:
            raise BridgeError("RAM_HANDLE_REPLACED")
        return self._fd

    def describe(self):
        return {"kind":"owned_sealed_memfd","size_bytes":self.size_bytes,
                "sha256":self.sha256,"open":not self.closed,"sealed":True,
                "model_loaded":False}

    def close(self):
        """Call only after the host has released all loader/inherited references."""
        if self.closed:
            return
        try:
            s=os.fstat(self._fd)
            if (s.st_dev,s.st_ino)==self._identity:
                os.close(self._fd)
        except OSError:
            pass
        finally:
            self.closed=True
            self._release_ram(self._lease)

    def __enter__(self):
        self.fileno()
        return self

    def __exit__(self,*_):
        self.close()
