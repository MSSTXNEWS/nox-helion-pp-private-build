"""Owned RAM artifact handle. The persistent host controls its loader lifetime."""
import os
import fcntl
import errno
import threading
import hashlib
import json
import uuid

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
        self._handle_id=uuid.uuid4().hex
        self.closed=False
        self._release_state="HELD"
        self._close_lock=threading.RLock()

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
                "model_loaded":False,"lease_release_state":self._release_state,
                "lease_released":self._release_state=="RELEASED"}

    def release_identity(self):
        """Trusted host may bind its loader-release proof to this exact handle.

        Returns no fd or raw reservation token. A newly created handle always
        has a different nonce, even when a host reuses a reservation identifier.
        """
        lease_id=self._lease.get("lease_id") if isinstance(self._lease,dict) else self._lease
        fence=self._lease.get("fencing_token") if isinstance(self._lease,dict) else None
        if not isinstance(lease_id,str) or not lease_id:
            raise BridgeError("RAM_LEASE_IDENTITY_UNAVAILABLE")
        digest=hashlib.sha256(json.dumps([lease_id,fence],separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
        return {"ram_handle_id":self._handle_id,"ram_lease_identity_sha256":digest,
                "ram_fencing_token":fence}

    def close(self):
        """Call only after the host has released all loader/inherited references."""
        with self._close_lock:
            if not self.closed:
                try:
                    s=os.fstat(self._fd)
                    if (s.st_dev,s.st_ino)!=self._identity:
                        raise BridgeError("RAM_HANDLE_REPLACED")
                    os.close(self._fd)
                except OSError as error:
                    if error.errno!=errno.EBADF:
                        raise BridgeError("RAM_HANDLE_CLOSE_UNCONFIRMED",outcome_uncertain=True) from None
                self.closed=True
            if self._release_state=="RELEASED":
                return {"closed":True,"lease_released":True}
            if self._release_state in ("RELEASING","UNKNOWN"):
                # A lost ACK may follow an actual release: do not repeat it blindly.
                raise BridgeError("RAM_RELEASE_RECONCILE_REQUIRED",outcome_uncertain=True)
            self._release_state="RELEASING"
            try:
                receipt=self._release_ram(self._lease)
                if not isinstance(receipt,dict) or receipt.get("released") is not True:
                    raise BridgeError("RAM_RELEASE_UNCONFIRMED",outcome_uncertain=True)
            except BaseException as error:
                self._release_state="UNKNOWN"
                if not isinstance(error,Exception):
                    raise
                raise BridgeError("RAM_RELEASE_UNCONFIRMED",outcome_uncertain=True) from None
            self._release_state="RELEASED"
            return {"closed":True,"lease_released":True}

    def reconcile_release(self,receipt):
        """Trusted host readback only; no lookup or retry is invented here.

        Receipt must identify this exact lease (and fence when supplied by the
        reservation). Verified released=False permits an explicit later close;
        verified released=True settles a lost ACK without another release call.
        """
        with self._close_lock:
            lease_id=self._lease.get("lease_id") if isinstance(self._lease,dict) else self._lease
            fence=self._lease.get("fencing_token") if isinstance(self._lease,dict) else None
            if (not self.closed or not isinstance(lease_id,str) or not lease_id
                or not isinstance(receipt,dict) or receipt.get("verified") is not True
                or receipt.get("lease_id")!=lease_id or type(receipt.get("released")) is not bool
                or (fence is not None and (type(fence) is not int
                    or type(receipt.get("fencing_token")) is not int or receipt.get("fencing_token")!=fence))):
                raise BridgeError("RAM_RELEASE_READBACK_UNVERIFIED")
            if self._release_state=="RELEASED" and receipt["released"] is False:
                raise BridgeError("RAM_RELEASE_READBACK_CONFLICT")
            self._release_state="RELEASED" if receipt["released"] else "HELD"
            return {"closed":True,"lease_released":receipt["released"]}

    def __enter__(self):
        self.fileno()
        return self

    def __exit__(self,*_):
        self.close()
