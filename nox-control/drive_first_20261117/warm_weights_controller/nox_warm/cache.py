"""Local atomic cache operations. Does not delete weights or force page eviction."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import time


class Paused(RuntimeError):
    pass


def file_sha256(path, before_chunk=lambda:None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            before_chunk()
            block=f.read(1024 * 1024)
            if not block:break
            h.update(block)
    return h.hexdigest()


class AtomicCache:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative):
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError('CACHE_PATH_MUST_BE_RELATIVE')
        parts = Path(relative).parts
        if '..' in parts:
            raise ValueError('CACHE_PATH_ESCAPE')
        p = (self.root / relative).resolve()
        if not p.is_relative_to(self.root) or p == self.root:
            raise ValueError('CACHE_PATH_ESCAPE')
        # Reject symlink parents even when the resolved target remains inside root.
        q = self.root
        for part in parts:
            q = q / part
            if q.is_symlink():
                raise ValueError('SYMLINK_CACHE_PATH')
        return p

    def verify(self, entry, *, allow_hash=True, before_chunk=lambda:None):
        p = self.path(entry['cache_path'])
        if not p.is_file() or p.stat().st_size != entry['size_bytes']:
            return False
        s=p.stat();identity={'size':s.st_size,'mtime_ns':s.st_mtime_ns,'inode':s.st_ino,'device':s.st_dev}
        receipt=p.with_name(p.name+'.verified.json')
        if receipt.is_symlink():raise ValueError('SYMLINK_CACHE_RECEIPT')
        if receipt.exists():
            try:
                old=json.loads(receipt.read_text())
                if old.get('identity')==identity and old.get('sha256')==entry['sha256']:return True
            except (OSError,ValueError):pass
        if not allow_hash:return False
        if file_sha256(p,before_chunk)!=entry['sha256']:return False
        tmp=receipt.with_name(receipt.name+'.tmp')
        if tmp.is_symlink():raise ValueError('SYMLINK_CACHE_RECEIPT')
        with tmp.open('w') as out:
            json.dump({'identity':identity,'sha256':entry['sha256']},out);out.flush();os.fsync(out.fileno())
        os.replace(tmp,receipt)
        return True

    def stage_local(self, entry, source, *, should_pause=lambda: False, chunk_bytes=1024 * 1024):
        """Copy an explicit local source, resume its .part, verify then atomically publish.

        The Drive adapter owns its own transfer. This helper is useful for trusted
        local artifacts and executable filesystem fixtures, not a second Drive client.
        """
        if not 4096 <= chunk_bytes <= 4 * 1024 * 1024:
            raise ValueError('INVALID_CHUNK_SIZE')
        target = self.path(entry['cache_path'])
        def chunk_guard():
            if should_pause():raise Paused('COPY_OR_HASH_PAUSED')
        if self.verify(entry,before_chunk=chunk_guard):
            return {'status': 'ALREADY_VERIFIED', 'cache_path': str(target)}
        if target.exists():
            raise ValueError('EXISTING_CACHE_CONFLICT_NO_REPLACE')
        source = Path(source).resolve()
        if not source.is_file() or source.stat().st_size != entry['size_bytes']:
            raise ValueError('SOURCE_SIZE_MISMATCH')
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + '.part')
        if part.is_symlink():
            raise ValueError('SYMLINK_PART')
        offset = part.stat().st_size if part.exists() else 0
        if offset > entry['size_bytes']:
            raise ValueError('PART_EXCEEDS_PINNED_SIZE')
        h = hashlib.sha256()
        if offset:
            with part.open('rb') as f:
                while True:
                    chunk_guard();block=f.read(chunk_bytes)
                    if not block:break
                    h.update(block)
        # A single host writer claim is required for this exact cache path.
        with source.open('rb') as inp, part.open('ab') as out:
            inp.seek(offset)
            while offset < entry['size_bytes']:
                if should_pause():
                    out.flush(); os.fsync(out.fileno())
                    raise Paused(f'DOWNLOAD_PAUSED_AT_BYTE:{offset}')
                block = inp.read(min(chunk_bytes, entry['size_bytes'] - offset))
                if not block:
                    raise ValueError('TRUNCATED_SOURCE')
                out.write(block); h.update(block); offset += len(block)
            out.flush(); os.fsync(out.fileno())
        if h.hexdigest() != entry['sha256']:
            raise ValueError('SHA_MISMATCH_PART_RETAINED_NOT_PUBLISHED')
        # No-clobber publication: a concurrent writer must not replace unique weights.
        os.link(part, target)
        part.unlink()
        dfd = os.open(target.parent, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
        self.verify(entry,before_chunk=chunk_guard)
        return {'status': 'CACHED_VERIFIED', 'cache_path': str(target),
                'size_bytes': offset, 'sha256': h.hexdigest()}


def warm_pages(path, max_bytes, *, admission, should_pause=lambda: False, chunk_bytes=1024 * 1024):
    """Read a bounded prefix through mmap; a cache hint, never a residency promise.

    admission(next_chunk_bytes) must inspect the live host/cgroup each time.
    Closing mmap does NOT reclaim page cache. Readahead and shared pages mean
    touched_bytes is not an exact memory charge; measured cgroup usage controls it.
    """
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError('INVALID_WARM_BUDGET')
    p = Path(path)
    length = min(p.stat().st_size, max_bytes)
    touched = 0; checksum = 0; began = time.monotonic()
    if not length:
        return {'status': 'NOT_WARMED', 'touched_bytes': 0, 'resident_guaranteed': False}
    with p.open('rb') as f, mmap.mmap(f.fileno(), length, access=mmap.ACCESS_READ) as view:
        for start in range(0, length, chunk_bytes):
            if should_pause():
                return {'status': 'WARM_PAUSED', 'touched_bytes': touched, 'resident_guaranteed': False}
            n = min(chunk_bytes, length - start)
            admission(n)
            for i in range(start, start + n, mmap.PAGESIZE):
                checksum ^= view[i]
            checksum ^= view[start + n - 1]
            touched += n
    return {'status': 'RAM_CACHE_HINT_ONLY', 'touched_bytes': touched,
            'resident_guaranteed': False, 'mmap_retained': False,
            'elapsed_seconds': time.monotonic() - began, 'touch_checksum': checksum}
