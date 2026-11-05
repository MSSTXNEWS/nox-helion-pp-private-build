"""P01-SB-08: read-only native source catalogue facet/page regression."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('source_catalog', Path(__file__).with_name('source_catalog.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Repo:
    def __init__(self, root): self.root = root
    def git(self, *args):
        p = subprocess.run(['git', '-C', str(self.root), *args], check=True,
                           capture_output=True, stdin=subprocess.DEVNULL)
        return p.stdout.decode('utf-8', 'strict')
    def head(self): return self.git('rev-parse', 'HEAD').strip()
    def admitted(self, head):
        return self.head() == head and not self.git('status','--porcelain','--untracked-files=no').strip()

class BrowserTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.repo = Repo(self.root)
        for cmd in (('init', '-q'), ('config','user.email','test@nox.local'), ('config','user.name','fixture')):
            self.repo.git(*cmd)
        for n in range(135):
            path = self.root / f'modules/{n:03}.py'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'print({n})', encoding='utf-8')
        for rel in ['templates/theme.css', 'patches/fix.patch', 'integrations/bridge.cs', 'docs/guide.md']:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rel, encoding='utf-8')
        self.repo.git('add','-A'); self.repo.git('commit','-qm','fixture')

    def test_two_pages_all_exact_objects(self):
        opts = ('modules/134.py',)
        first = mod.inspect_managed_sources(self.repo, opts)
        second = mod.inspect_managed_sources(self.repo, opts, offset=first['next_offset'])
        assert len(first['items']) == 120
        assert len(second['items']) == 19
        assert first['has_more'] and not second['has_more']
        assert first['next_offset'] == 120 and second['next_offset'] is None
        assert first['items'][0]['path'] == 'modules/134.py'
        all_paths = [x['path'] for r in [first,second] for x in r['items']]
        assert len(all_paths) == len(set(all_paths)) == 139
        assert all(x['git_blob_sha'] == self.repo.git('rev-parse',f'HEAD:{x["path"]}').strip() for r in [first,second] for x in r['items'])

    def test_filters_preserve_global_totals_and_no_import(self):
        for cat, expected in [('code_modules',135),('templates',1),('patches',1),('integrations',1),('contracts_docs',1)]:
            with self.subTest(category=cat):
                res = mod.inspect_managed_sources(self.repo, category=cat)
                assert res['status'] == 'SOURCE_INVENTORY_READ_ONLY'
                assert res['matching_total'] == expected
                assert res['supported_total'] == 139
                assert len(res['items']) == min(120, expected)
                assert all(r['category'] == cat for r in res['items'])
                assert not res['imported_into_s03'] and not res['all_sources_loaded']

    def test_invalid_filter_offset_never_invokes_git(self):
        class NoGit(Repo):
            def git(self,*args): raise AssertionError('must reject before reading')
        src = NoGit(self.root)
        for kw in [dict(category='random'),dict(category='../templates'),dict(category=7),dict(offset=True),dict(offset=-1),dict(offset=12001),dict(offset='1')]:
            with self.subTest(kw=kw):
                r = mod.inspect_managed_sources(src, **kw)
                assert r['status'] == 'HOLD' and r['reason'] == 'SOURCE_CATALOG_FILTER_INVALID'
                assert r['items'] == []

    def test_filtered_pagination_and_owner_first(self):
        a = mod.inspect_managed_sources(self.repo, ('modules/134.py',), category='code_modules')
        assert a['items'][0]['path'] == 'modules/134.py'
        assert a['owner_admitted_total'] == 1
        b = mod.inspect_managed_sources(self.repo, ('modules/134.py',), category='code_modules', offset=120)
        assert b['matching_total'] == 135 and len(b['items']) == 15
        assert not any(x['owner_admitted'] for x in b['items'])

    def test_race_with_second_admission_and_empty_page(self):
        class Race(Repo):
            reads=0
            def admitted(self, head):
                self.reads+=1
                return self.reads==1
        bad = mod.inspect_managed_sources(Race(self.root), category='templates')
        assert bad['status'] == 'HOLD' and bad['reason'] == 'EXACT_CLEAN_HEAD_REQUIRED'
        empty = mod.inspect_managed_sources(self.repo, category='patches', offset=10)
        assert empty['matching_total'] == 1 and empty['items'] == []
        assert not empty['has_more'] and empty['next_offset'] is None

if __name__ == '__main__': unittest.main()
