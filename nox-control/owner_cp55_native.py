"""SHA-pinned CP55/S03 export called only by existing owner SSH transport."""
import fcntl, os, stat, tempfile, time
from pathlib import Path
import owner_cp55_scope as scope
import owner_cp55_cipher as cipher

def export(public,scope_sha,source,request,out):
    scope.DEADLINE=time.monotonic()+900
    before=scope.flag_snapshot();count=scope.stopped_services()
    scope.require(count==28,'STOPPED_SERVICE_COUNT')
    lock_path=scope.plain(scope.STATE/'owner_maintenance.lock')
    fd=os.open(lock_path,os.O_RDWR|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd);scope.require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid(),'LEASE_SCOPE')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('HOLD_CP55_EXISTING_LEASE_BUSY') from None
        last=[0.0]
        def guard():
            scope.remaining();scope.require(scope.flag_snapshot()==before,'STOP_CHANGED')
            current=os.stat(lock_path);scope.require((current.st_dev,current.st_ino)==(info.st_dev,info.st_ino),'LEASE_REPLACED')
            if time.monotonic()-last[0]>=1:
                scope.require(scope.stopped_services()==count,'SERVICES_CHANGED');last[0]=time.monotonic()
        guard();helper=scope.helper_module();rows=scope.checkpoint_rows(helper)
        s03=scope.plain(scope.ROOT/'kb/knowledge.sqlite');size=s03.stat().st_size
        scope.require(0<size<scope.MAX_FILE,'S03_SCOPE')
        scope.require(sum(p.stat().st_size for p,_,_ in rows)+size<=scope.MAX_TOTAL,'TOTAL_BOUND')
        available=os.statvfs('/dev/shm');scope.require(available.f_bavail*available.f_frsize>=size+64*1024**2,'RAMFS_RESERVE')
        current=int(Path('/sys/fs/cgroup/memory.current').read_text());maximum=Path('/sys/fs/cgroup/memory.max').read_text().strip()
        scope.require(maximum.isdigit() and int(maximum)-current>=size+512*1024**2,'RAM_RESERVE')
        with tempfile.TemporaryDirectory(prefix='nox-cp55-s03-',dir='/dev/shm') as tmp:
            snap=Path(tmp)/'s03.sqlite';helper.snapshot_sqlite(s03,snap);guard()
            result=cipher.seal([(snap,'s03.sqlite',None)]+rows,public,scope_sha,source,request,out,guard)
        guard();return {**result,'sqlite_snapshot_verified':True,'stop_flags_unchanged':True,'stopped_services':count,
                       'persistent_source_writes':0,'temporary_ram_snapshot_removed':True,'private_key_received':False}
    finally:os.close(fd)
