"""P01-SB-08: real-Git exact-HEAD owner-selected source detail + safety."""
import hashlib
import importlib.util
import subprocess
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'nox_selection_catalog', Path(__file__).with_name('source_catalog.py'))
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class Repo:
    def __init__(self, root): self.root = root
    def git(self, *args):
        p = subprocess.run(['git','-C',str(self.root),*args],
                           stdin=subprocess.DEVNULL, capture_output=True, check=True)
        return p.stdout.decode('utf-8', 'strict')
    def head(self): return self.git('rev-parse','HEAD').strip()
    def admitted(self, head):
        return self.head() == head and self.git('status','--porcelain','--untracked-files=no').strip() == ''


class SelectionTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        self.root=Path(td.name); self.repo=Repo(self.root)
        for cmd in [('init','-q'),('config','user.name','NOX Fixture'),
                    ('config','user.email','fixture@nox.local')]:self.repo.git(*cmd)
        self.body='π = "verified source"\nprint(π)\n'
        (self.root/'modules').mkdir()
        (self.root/'modules'/'valid.py').write_text(self.body,encoding='utf-8')
        (self.root/'modules'/'not_approved.py').write_text('print("no")',encoding='utf-8')
        self.repo.git('add','-A');self.repo.git('commit','-qm','test initial')
        self.blob=self.repo.git('rev-parse','HEAD:modules/valid.py').strip()
        self.head=self.repo.head()

    def detail(self, **kwargs):
        return catalog.inspect_selected_source(self.repo,'modules/valid.py',
                                                ('modules/valid.py',),**kwargs)

    def test_exact_head_sha256_bytes_preview_no_ingestion(self):
        out=self.detail(expected_head=self.head,expected_git_blob_sha=self.blob)
        self.assertEqual(out['status'],'SOURCE_SELECTION_READ_ONLY')
        self.assertEqual(out['source_head'],self.head)
        self.assertEqual(out['git_blob_sha'],self.blob)
        self.assertEqual(out['source_sha256'],hashlib.sha256(self.body.encode()).hexdigest())
        self.assertEqual(out['source_bytes'],len(self.body.encode()))
        self.assertEqual(out['preview'],self.body)
        self.assertFalse(out['imported_into_s03'])
        self.assertFalse(out['ingestion_authorized'])
        self.assertFalse(out['source_executed'])
        self.assertFalse(out['model_called'])

    def test_unapproved_only_metadata_never_git_cat_file(self):
        class NoRead(Repo):
            def git(self,*args):
                if args[0]=='cat-file':raise AssertionError('unapproved contents accessed')
                return super().git(*args)
        src=NoRead(self.root)
        out=catalog.inspect_selected_source(src,'modules/not_approved.py',('modules/valid.py',))
        self.assertEqual(out['status'],'SOURCE_SELECTION_OWNER_APPROVAL_REQUIRED')
        self.assertIsNone(out['source_sha256'])
        self.assertIsNone(out['preview'])
        self.assertFalse(out['imported_into_s03'])

    def test_expected_head_and_blob_drift_hold(self):
        a=self.detail(expected_head='a'*40)
        b=self.detail(expected_git_blob_sha='b'*40)
        self.assertEqual(a['reason'],'SOURCE_SELECTION_HEAD_DRIFT')
        self.assertEqual(b['reason'],'SOURCE_SELECTION_BLOB_DRIFT')
        self.assertFalse(a['imported_into_s03'])

    def test_invalid_inputs_rejected_before_git(self):
        class NoGit(Repo):
            def git(self,*args):raise AssertionError('must reject first')
        src=NoGit(self.root)
        for path,opts in [('../secrets.py',{}),('/tmp/s.py',{}),('path\x00.py',{}),
                          ('modules/a.exe',{}),('modules/valid.py',{'expected_head':'invalid'}),
                          ('modules/valid.py',{'expected_git_blob_sha':'1'*63})]:
            with self.subTest(path=path,opts=opts):
                out=catalog.inspect_selected_source(src,path,('modules/valid.py',),**opts)
                self.assertEqual(out['reason'],'SOURCE_SELECTION_INPUT_INVALID')

    def test_missing_and_symlink_source_are_hold(self):
        missing=catalog.inspect_selected_source(self.repo,'modules/missing.py',('modules/missing.py',))
        self.assertEqual(missing['reason'],'SOURCE_SELECTION_NOT_REGULAR_BLOB')
        try:(self.root/'modules'/'alias.py').symlink_to('valid.py')
        except OSError:self.skipTest('symlink unavailable')
        self.repo.git('add','-A');self.repo.git('commit','-qm','alias fixture')
        link=catalog.inspect_selected_source(self.repo,'modules/alias.py',('modules/alias.py',))
        self.assertEqual(link['reason'],'SOURCE_SELECTION_NOT_REGULAR_BLOB')

    def test_dirty_tracked_worktree_holds(self):
        (self.root/'modules'/'valid.py').write_text('modified')
        self.assertEqual(self.detail()['reason'],'EXACT_CLEAN_HEAD_REQUIRED')

    def test_oversized_blob_skips_source_read(self):
        (self.root/'modules'/'valid.py').write_text('x'*(128*1024+1))
        self.repo.git('add','-A');self.repo.git('commit','-qm','big blob')
        class NoContent(Repo):
            def git(self,*args):
                if args[:2]==('cat-file','blob'):raise AssertionError('oversized blob read')
                return super().git(*args)
        result=catalog.inspect_selected_source(NoContent(self.root),'modules/valid.py',('modules/valid.py',))
        self.assertEqual(result['reason'],'SOURCE_BLOB_PREVIEW_QUOTA')

    def test_second_clean_check_catches_race(self):
        class Racy(Repo):
            count=0
            def admitted(self, head):
                self.count+=1
                return self.count==1
        result=catalog.inspect_selected_source(Racy(self.root),'modules/valid.py',('modules/valid.py',))
        self.assertEqual(result['reason'],'SOURCE_DETAIL_INTEGRITY_HOLD')

    def test_unicode_git_blob_integrity_mismatch_holds(self):
        class Edited(Repo):
            def git(self,*args):
                if args[:2]==('cat-file','blob'):return 'fake content'
                return super().git(*args)
        result=catalog.inspect_selected_source(Edited(self.root),'modules/valid.py',('modules/valid.py',))
        self.assertEqual(result['reason'],'SOURCE_DETAIL_INTEGRITY_HOLD')


if __name__=='__main__':unittest.main()
