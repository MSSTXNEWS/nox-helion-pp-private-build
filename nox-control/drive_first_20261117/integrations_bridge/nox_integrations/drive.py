"""Drive through existing rclone, confined to configured remote/project roots."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat as statmod
import sys
import tempfile
import time
import uuid

from .config import relative_path
from .core import BoundedRunner, BridgeError
from .memfd import MemfdHandle, RAM_TRANSPORT_OVERHEAD, F_ADD_SEALS, F_GET_SEALS, REQUIRED_SEALS

SMALL_READ_MAX = 1024 * 1024


def _positive(value, maximum):
    if type(value) is not int or not 0 < value <= maximum:
        raise BridgeError("INVALID_SIZE_OR_LIMIT")
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise BridgeError("INVALID_SHA256")
    return value


def _file_sha(file,expected_size,should_pause=None):
    before=os.fstat(file.fileno())
    digest=hashlib.sha256();size=0
    while chunk:=file.read(1024*1024):
        if should_pause and should_pause():
            raise BridgeError("CANCELLED")
        size+=len(chunk)
        if size>expected_size:
            raise BridgeError("LOCAL_FILE_CHANGED")
        digest.update(chunk)
    after=os.fstat(file.fileno())
    if size!=expected_size or (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise BridgeError("LOCAL_FILE_CHANGED")
    return digest.hexdigest()


@contextmanager
def _parent(root, rel, *, create=False):
    """Directory-descriptor traversal; never follow links, including ancestors."""
    rel = relative_path(rel)
    root = Path(root)
    if not root.is_absolute():
        raise BridgeError("LOCAL_ROOT_MUST_BE_ABSOLUTE")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        pieces = list(root.parts[1:]) + rel.split("/")[:-1]
        root_len = len(root.parts[1:])
        for i, name in enumerate(pieces):
            try:
                next_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create or i < root_len:
                    raise BridgeError("LOCAL_ROOT_OR_PARENT_MISSING") from None
                os.mkdir(name, 0o700, dir_fd=fd)
                next_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError:
                raise BridgeError("LOCAL_PATH_SYMLINK_OR_UNAVAILABLE") from None
            os.close(fd)
            fd = next_fd
            if i >= root_len - 1:
                s = os.fstat(fd)
                if s.st_uid != os.geteuid() or s.st_mode & 0o022:
                    raise BridgeError("LOCAL_ROOT_NOT_OWNER_CONTROLLED")
        yield fd, rel.split("/")[-1]
    finally:
        os.close(fd)


def _read_local(root, rel, maximum):
    with _parent(root, rel) as (parent, leaf):
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except OSError:
            raise BridgeError("ARTIFACT_UNAVAILABLE") from None
    file = os.fdopen(fd, "rb")
    s = os.fstat(fd)
    if not statmod.S_ISREG(s.st_mode) or s.st_size > maximum:
        file.close()
        raise BridgeError("ARTIFACT_TYPE_OR_SIZE")
    return file


class HashSink:
    def __init__(self):
        self.digest = hashlib.sha256()
        self.size = 0
    def write(self, chunk):
        self.digest.update(chunk)
        self.size += len(chunk)


class DriveAdapter:
    def __init__(self, config, *, runner=None, should_pause=None):
        self.config = config
        self.runner = runner or BoundedRunner()
        self.should_pause = should_pause

    def _pause(self,other=None):
        return lambda: bool((self.should_pause and self.should_pause()) or (other and other()))

    def _target(self, path=""):
        remote = self.config.get("NOX_DRIVE_REMOTE")
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}", remote):
            raise BridgeError("DRIVE_REMOTE_NOT_CONFIGURED")
        root = relative_path(self.config.get("NOX_DRIVE_ROOT"))
        rel = relative_path(path, allow_empty=True)
        return remote + ":" + root + ("/" + rel if rel else "")

    def _run(self, args, *, maximum=SMALL_READ_MAX, timeout=30, sink=None, should_pause=None):
        if not all(self.config.drive_requirements().values()):
            raise BridgeError("DRIVE_PENDING_CONFIGURATION")
        binary = self.config.rclone_binary()
        rclone_config = self.config.rclone_config()
        # Forward only rclone's specific optional config password, not all tokens.
        env = {"PATH": os.defpath, "HOME": str(Path.home()), "LANG":"C.UTF-8"}
        if self.config.get("RCLONE_CONFIG_PASS"):
            env["RCLONE_CONFIG_PASS"] = self.config.get("RCLONE_CONFIG_PASS")
        argv = [binary, *args, "--config", rclone_config, "--retries", "1",
                "--low-level-retries", "1", "--contimeout", "10s",
                "--timeout", "20s", "--buffer-size", "256Ki", "--transfers", "1",
                "--checkers", "1", "--stats", "0", "--log-level", "ERROR"]
        return self.runner.run(argv, env=env, timeout=timeout, max_output=maximum,
                               sink=sink, should_pause=self._pause(should_pause))

    def _json(self, args, *, maximum=SMALL_READ_MAX):
        try:
            return json.loads(self._run(args, maximum=maximum))
        except (ValueError, UnicodeError):
            raise BridgeError("DRIVE_INVALID_JSON") from None

    def stat(self, remote_path):
        obj = self._json(["lsjson", self._target(remote_path), "--stat", "--hash"], maximum=65536)
        if not isinstance(obj,dict) or type(obj.get("IsDir")) is not bool or type(obj.get("Size")) is not int:
            raise BridgeError("DRIVE_INVALID_METADATA")
        if not obj["IsDir"] and obj["Size"] < 0:
            raise BridgeError("DRIVE_INVALID_METADATA")
        return {"path":remote_path, "size_bytes":obj["Size"], "is_dir":obj["IsDir"],
                "remote_verified":True}

    def check(self):
        result=self.stat("")
        if not result["is_dir"]:
            raise BridgeError("DRIVE_PROJECT_ROOT_NOT_DIRECTORY")
        return {"status":"checked", "remote_verified":True, "project_root_accessible":True}

    def list(self, path="", limit=100):
        _positive(limit,500)
        rows=self._json(["lsjson",self._target(path),"--max-depth","1","--no-mimetype"],maximum=1024*1024)
        if not isinstance(rows,list):
            raise BridgeError("DRIVE_INVALID_LIST")
        selected=[]
        for item in rows[:limit]:
            if not isinstance(item,dict) or not isinstance(item.get("Path"),str):
                raise BridgeError("DRIVE_INVALID_LIST")
            selected.append({"path":item["Path"],"size_bytes":item.get("Size"),"is_dir":item.get("IsDir"),"modified":item.get("ModTime")})
        return {"status":"listed","items":selected,"returned":len(selected),
                "truncated":len(rows)>limit,"remote_verified":True}

    def read(self, path, max_bytes=SMALL_READ_MAX):
        _positive(max_bytes,SMALL_READ_MAX)
        metadata=self.stat(relative_path(path))
        if metadata["is_dir"] or metadata["size_bytes"]>max_bytes:
            raise BridgeError("DRIVE_READ_TYPE_OR_SIZE")
        data=self._run(["cat",self._target(path),"--count",str(max_bytes+1)],maximum=max_bytes+1)
        if len(data)>max_bytes or len(data)!=metadata["size_bytes"]:
            raise BridgeError("DRIVE_READ_CHANGED_OR_TOO_LARGE")
        try:
            content=data.decode("utf-8")
        except UnicodeError:
            raise BridgeError("DRIVE_READ_REQUIRES_UTF8") from None
        return {"status":"read","path":path,"content":content,"size_bytes":len(data),
                "sha256":hashlib.sha256(data).hexdigest(),"remote_verified":True}

    def _remote_hash(self, path, expected_size, *, timeout):
        sink=HashSink()
        self._run(["cat",self._target(path),"--count",str(expected_size+1)],
                  maximum=expected_size+1,timeout=timeout,sink=sink)
        if sink.size!=expected_size:
            raise BridgeError("REMOTE_SIZE_MISMATCH")
        return sink.digest.hexdigest()

    def upload_artifact(self, artifact_path, remote_path, expected_sha256):
        """Copy immutable artifact + deterministic manifest; hash both readbacks."""
        relative_path(artifact_path);relative_path(remote_path);_sha(expected_sha256)
        root=self.config.get("NOX_ARTIFACT_ROOT")
        if not root:
            raise BridgeError("ARTIFACT_ROOT_NOT_CONFIGURED")
        maximum=self.config.positive_int("NOX_UPLOAD_MAX_BYTES",512*1024*1024)
        timeout=self.config.positive_int("NOX_TRANSFER_TIMEOUT_SECONDS",300)
        with _read_local(root,artifact_path,maximum) as source:
            before=os.fstat(source.fileno())
            if os.statvfs(root).f_bavail*os.statvfs(root).f_frsize < before.st_size+16*1024*1024:
                raise BridgeError("UPLOAD_SNAPSHOT_DISK_BUDGET")
            # A private stable snapshot prevents a concurrently edited source from leaking.
            with tempfile.TemporaryDirectory(prefix=".nox-upload-",dir=root) as directory:
                snapshot=Path(directory)/"artifact"
                digest=hashlib.sha256();size=0;tail=b""
                secret_bytes=tuple(s.encode() for s in self.config.secrets)
                keep=max((len(s) for s in secret_bytes),default=1)-1
                with snapshot.open("xb") as output:
                    os.chmod(snapshot,0o600)
                    while chunk:=source.read(1024*1024):
                        if self.should_pause and self.should_pause():
                            raise BridgeError("CANCELLED")
                        scan=tail+chunk
                        if any(secret in scan for secret in secret_bytes):
                            raise BridgeError("SECRET_IN_ARTIFACT")
                        tail=scan[-keep:] if keep else b""
                        size+=len(chunk)
                        if size>maximum:
                            raise BridgeError("ARTIFACT_CHANGED_OR_TOO_LARGE")
                        digest.update(chunk);output.write(chunk)
                    output.flush();os.fsync(output.fileno())
                after=os.fstat(source.fileno())
                if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns) or digest.hexdigest()!=expected_sha256:
                    raise BridgeError("ARTIFACT_SHA_OR_REVISION_MISMATCH")
                manifest={"schema":"nox.drive.backup.v1","path":remote_path,"size_bytes":size,"sha256":expected_sha256}
                manifest_bytes=(json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n").encode()
                manifest_file=Path(directory)/"manifest.json"
                manifest_file.write_bytes(manifest_bytes);os.chmod(manifest_file,0o600)
                try:
                    self._run(["copyto",str(snapshot),self._target(remote_path),"--immutable","--checksum"],maximum=65536,timeout=timeout)
                    observed=self._remote_hash(remote_path,size,timeout=timeout)
                    if observed!=expected_sha256:
                        raise BridgeError("REMOTE_SHA_MISMATCH")
                    sidecar=remote_path+".sha256.json"
                    self._run(["copyto",str(manifest_file),self._target(sidecar),"--immutable","--checksum"],maximum=65536,timeout=timeout)
                    if self._remote_hash(sidecar,len(manifest_bytes),timeout=timeout)!=hashlib.sha256(manifest_bytes).hexdigest():
                        raise BridgeError("MANIFEST_READBACK_MISMATCH")
                except BridgeError as error:
                    raise BridgeError(error.code,outcome_uncertain=True,http_status=error.http_status) from None
        return {"status":"uploaded_verified",**manifest,"manifest_path":sidecar,
                "readback_sha256":observed,"remote_verified":True,
                "receipt_id":uuid.uuid4().hex,"verified_at":time.time()}

    def download_verified(self, remote_path, cache_path, expected_sha256, size_bytes, *, should_pause=None):
        """Explicit disk-cache option; the normal model path is Drive→owned RAM."""
        if self.config.get("NOX_ALLOW_DISK_CACHE")!="1":
            raise BridgeError("DISK_CACHE_REQUIRES_EXPLICIT_OPT_IN")
        pause=self._pause(should_pause)
        if pause():
            raise BridgeError("CANCELLED")
        relative_path(remote_path);relative_path(cache_path);_sha(expected_sha256)
        maximum=self.config.positive_int("NOX_DOWNLOAD_MAX_BYTES",1024*1024*1024)
        _positive(size_bytes,maximum)
        root=self.config.get("NOX_DRIVE_CACHE_ROOT")
        if not root:
            raise BridgeError("CACHE_ROOT_NOT_CONFIGURED")
        timeout=self.config.positive_int("NOX_TRANSFER_TIMEOUT_SECONDS",300)
        headroom=self.config.positive_int("NOX_CACHE_HEADROOM_BYTES",64*1024*1024)
        metadata=self.stat(remote_path)
        if metadata["is_dir"] or metadata["size_bytes"]!=size_bytes:
            raise BridgeError("DOWNLOAD_MANIFEST_SIZE_MISMATCH")
        with _parent(root,cache_path,create=True) as (parent,leaf):
            try:
                existing=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
            except FileNotFoundError:
                existing=None
            except OSError:
                raise BridgeError("CACHE_DESTINATION_UNAVAILABLE") from None
            if existing is not None:
                with os.fdopen(existing,"rb") as f:
                    s=os.fstat(f.fileno())
                    if not statmod.S_ISREG(s.st_mode) or s.st_size!=size_bytes:
                        raise BridgeError("CACHE_DESTINATION_CONFLICT")
                    h=_file_sha(f,size_bytes,pause)
                if h!=expected_sha256:
                    raise BridgeError("CACHE_DESTINATION_CONFLICT")
                return self._download_receipt(cache_path,root,size_bytes,h,"cache_hit_verified")
            v=os.fstatvfs(parent)
            if v.f_bavail*v.f_frsize<size_bytes+headroom:
                raise BridgeError("DOWNLOAD_DISK_BUDGET")
            part=".nox-"+uuid.uuid4().hex+".part"
            fd=os.open(part,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
            try:
                with os.fdopen(fd,"wb") as output:
                    self._run(["cat",self._target(remote_path),"--count",str(size_bytes+1)],
                              maximum=size_bytes+1,timeout=timeout,sink=output,should_pause=should_pause)
                    output.flush();os.fsync(output.fileno())
                fd=os.open(part,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
                with os.fdopen(fd,"rb") as downloaded:
                    if os.fstat(downloaded.fileno()).st_size!=size_bytes:
                        raise BridgeError("DOWNLOAD_SIZE_MISMATCH")
                    digest=_file_sha(downloaded,size_bytes,pause)
                if digest!=expected_sha256:
                    raise BridgeError("DOWNLOAD_SHA_MISMATCH")
                if pause():
                    raise BridgeError("CANCELLED")
                # link+unlink is atomic no-clobber publication on the same filesystem.
                # Unlike replace(), it cannot destroy another writer's completed artifact.
                try:
                    os.link(part,leaf,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
                except FileExistsError:
                    raise BridgeError("CACHE_CONCURRENT_WRITER") from None
                os.unlink(part,dir_fd=parent);os.fsync(parent)
            finally:
                try:
                    os.unlink(part,dir_fd=parent)
                except FileNotFoundError:
                    pass
        return self._download_receipt(cache_path,root,size_bytes,digest,"downloaded_verified")

    def download_memfd_verified(self,remote_path,expected_sha256,size_bytes,*,
                                reserve_ram,release_ram,should_pause=None):
        """Opt-in Drive→RAM. Requires host-owned RAM reservation and cancellation."""
        if (not callable(reserve_ram) or not callable(release_ram)
                or not (callable(should_pause) or callable(self.should_pause))):
            raise BridgeError("RAM_HOST_BINDING_REQUIRED")
        if sys.platform!="linux" or not hasattr(os,"memfd_create") or not hasattr(os,"MFD_ALLOW_SEALING"):
            raise BridgeError("SEALED_MEMFD_UNAVAILABLE")
        pause=self._pause(should_pause)
        if pause():
            raise BridgeError("CANCELLED")
        relative_path(remote_path);_sha(expected_sha256)
        maximum=self.config.positive_int("NOX_DOWNLOAD_MAX_BYTES",1024*1024*1024)
        _positive(size_bytes,maximum)
        metadata=self.stat(remote_path)
        if metadata["is_dir"] or metadata["size_bytes"]!=size_bytes:
            raise BridgeError("DOWNLOAD_MANIFEST_SIZE_MISMATCH")
        lease=reserve_ram(size_bytes+RAM_TRANSPORT_OVERHEAD)
        if lease is None or lease is False:
            raise BridgeError("RAM_RESERVATION_DENIED")
        fd=None
        try:
            if pause():
                raise BridgeError("CANCELLED")
            fd=os.memfd_create("nox-drive-"+uuid.uuid4().hex,
                               flags=os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
            timeout=self.config.positive_int("NOX_TRANSFER_TIMEOUT_SECONDS",300)
            with os.fdopen(os.dup(fd),"w+b") as output:
                self._run(["cat",self._target(remote_path),"--count",str(size_bytes+1)],
                          maximum=size_bytes+1,timeout=timeout,sink=output,should_pause=pause)
                output.flush()
                if os.fstat(output.fileno()).st_size!=size_bytes:
                    raise BridgeError("DOWNLOAD_SIZE_MISMATCH")
                output.seek(0)
                digest=_file_sha(output,size_bytes,pause)
            if digest!=expected_sha256:
                raise BridgeError("DOWNLOAD_SHA_MISMATCH")
            if pause():
                raise BridgeError("CANCELLED")
            seals=REQUIRED_SEALS
            fcntl.fcntl(fd,F_ADD_SEALS,seals)
            if fcntl.fcntl(fd,F_GET_SEALS)&seals!=seals:
                raise BridgeError("RAM_SEAL_FAILED")
            os.lseek(fd,0,os.SEEK_SET)
            return MemfdHandle(fd,size_bytes=size_bytes,sha256=digest,lease=lease,release_ram=release_ram)
        except BaseException:
            if fd is not None:
                os.close(fd)
            try:
                released=release_ram(lease)
                if not isinstance(released,dict) or released.get("released") is not True:
                    raise BridgeError("RAM_ABORT_RELEASE_UNCONFIRMED",outcome_uncertain=True)
            except Exception:
                raise BridgeError("RAM_ABORT_RELEASE_UNCONFIRMED",outcome_uncertain=True) from None
            raise

    @staticmethod
    def _download_receipt(cache_path,root,size,digest,status):
        return {"status":status,"cache_path":cache_path,"local_path":str(Path(root)/cache_path),
                "sha256":digest,"size_bytes":size,"remote_verified":True,
                "publication":"atomic_no_clobber","receipt_id":uuid.uuid4().hex,"verified_at":time.time()}
