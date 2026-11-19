"""Real local kernel-file tests; these do not claim a native chroot run."""
import errno
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import owner_project_test_runner as runner


def descriptors():
    found=set()
    for fd in range(96):
        try:fcntl.fcntl(fd,fcntl.F_GETFD)
        except OSError:continue
        found.add(fd)
    return found


class KernelSelfFdTests(unittest.TestCase):
    def test_reads_dynamic_kernel_stat_not_a_snapshot(self):
        cap=runner.KernelSelfFdAdapter()
        try:
            first=cap.stat_fields(cap._checked_read(cap.stat_path))
            deadline=time.monotonic()+1
            while True:
                sum(i*i for i in range(10000))
                after=cap.stat_fields(cap._checked_read(cap.stat_path))
                if after[3]>first[3] or time.monotonic()>=deadline:break
            self.assertEqual((after[0],after[2]),(os.getpid(),first[2]))
            self.assertGreater(after[3],first[3])
            fresh=cap.stat_fields(Path(cap.stat_path).read_bytes())
            self.assertEqual((fresh[0],fresh[2]),(after[0],after[2]))
            self.assertEqual(cap._checked_read(cap.BOOT_PATH),Path(cap.BOOT_PATH).read_bytes())
        finally:cap.close()

    def test_only_two_real_fds_and_actual_counts_restore(self):
        before=descriptors();cap=runner.KernelSelfFdAdapter();owned=set(cap.descriptors)
        self.assertEqual(len(owned),2)
        self.assertEqual(descriptors()-before,owned)
        self.assertEqual(len(descriptors()),len(before)+2)
        cap.close()
        self.assertEqual(descriptors(),before)

    def test_foreign_and_alias_paths_are_not_capabilities(self):
        cap=runner.KernelSelfFdAdapter()
        try:
            for path in ('/proc/2147483647/stat','/proc/self/stat',
                         '/proc/self/fd','/proc/'+str(os.getpid())+'/../1/stat'):
                with self.subTest(path=path),self.assertRaises(runner.RunnerHold):
                    cap._checked_read(path)
        finally:cap.close()

    def test_fake_regular_file_is_rejected_even_with_matching_stat_bytes(self):
        cap=runner.KernelSelfFdAdapter();original=cap.entries[cap.stat_path]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'stat';path.write_bytes(cap._checked_read(cap.stat_path))
                fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC)
                try:
                    info=os.fstat(fd);cap.entries[cap.stat_path]=(fd,info.st_dev,info.st_ino,16384)
                    with self.assertRaisesRegex(runner.RunnerHold,'CAPABILITY'):
                        cap._checked_read(cap.stat_path)
                finally:
                    cap.entries[cap.stat_path]=original;os.close(fd)
        finally:cap.close()

    def test_closed_fd_fails_without_cached_response(self):
        cap=runner.KernelSelfFdAdapter()
        try:
            cap._checked_read(cap.stat_path)
            os.close(cap.entries[cap.stat_path][0])
            with self.assertRaisesRegex(runner.RunnerHold,'CLOSED_OR_CHANGED'):
                cap._checked_read(cap.stat_path)
        finally:cap.close()

    def test_identity_and_descriptor_flags_are_rechecked(self):
        cap=runner.KernelSelfFdAdapter()
        try:
            original=cap.start_ticks;cap.start_ticks+=1
            with self.assertRaisesRegex(runner.RunnerHold,'IDENTITY_CHANGED'):
                cap._checked_read(cap.stat_path)
            cap.start_ticks=original
            fd=cap.entries[cap.stat_path][0];os.set_inheritable(fd,True)
            try:
                with self.assertRaisesRegex(runner.RunnerHold,'CAPABILITY'):
                    cap._checked_read(cap.stat_path)
            finally:os.set_inheritable(fd,False)
        finally:cap.close()

    def test_regular_capability_cannot_escape_as_a_directory_or_write(self):
        cap=runner.KernelSelfFdAdapter();cwd=os.getcwd()
        try:
            fd=cap.entries[cap.stat_path][0]
            with self.assertRaises(OSError) as caught:os.open('../root',os.O_RDONLY,dir_fd=fd)
            self.assertEqual(caught.exception.errno,errno.ENOTDIR)
            with self.assertRaises(OSError) as caught:os.fchdir(fd)
            self.assertEqual(caught.exception.errno,errno.ENOTDIR)
            with self.assertRaises(OSError) as caught:os.write(fd,b'x')
            self.assertEqual(caught.exception.errno,errno.EBADF)
            self.assertEqual(os.getcwd(),cwd)
        finally:cap.close()

    def test_exact_path_adapter_restores_api_and_delegates_normal_files(self):
        original=Path.read_text;cap=runner.KernelSelfFdAdapter();owned=cap.descriptors
        try:
            cap.install()
            observed=cap.stat_fields(Path(cap.stat_path).read_text().encode())
            fresh=cap.stat_fields(cap._checked_read(cap.stat_path))
            self.assertEqual((observed[0],observed[2]),(fresh[0],fresh[2]))
            self.assertEqual(Path(cap.BOOT_PATH).read_text().encode(),cap._checked_read(cap.BOOT_PATH))
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'ordinary.txt';path.write_text('ordinary source fixture')
                self.assertEqual(path.read_text(),'ordinary source fixture')
            # The capability itself must not claim this host process is a
            # confined verifier while a full /proc remains visible here.
            with self.assertRaisesRegex(runner.RunnerHold,'CONFINEMENT_SCOPE'):cap.proof()
        finally:cap.close()
        self.assertIs(Path.read_text,original)
        for fd in owned:
            with self.assertRaises(OSError):os.fstat(fd)

    def test_descriptor_closure_keeps_no_extra_or_directory_handle(self):
        code=r'''
import fcntl,json,os,sys
sys.path.insert(0,sys.argv[1])
import owner_project_test_runner as r
c=r.KernelSelfFdAdapter();owned=set(c.descriptors)
extra=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
r.close_unapproved_descriptors(c)
found=set()
for fd in range(3,96):
    try:fcntl.fcntl(fd,fcntl.F_GETFD)
    except OSError:continue
    found.add(fd)
assert found==owned and extra not in found
c._checked_read(c.stat_path);c.close()
print(json.dumps({'kept':len(found),'directory_fd_closed':True}))
'''
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(Path(runner.__file__).parent)],
                              capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('"directory_fd_closed": true',result.stdout)


if __name__=='__main__':unittest.main()
