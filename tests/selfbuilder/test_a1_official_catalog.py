"""A.1 official public source metadata read-only regressions."""
import unittest
from nox_selfbuilder.a1_official_catalog import probe_official_catalog
from nox_selfbuilder.worms import WormHold
HEAD='a'*40
class OfficialCatalogTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]; self.stopped=False; self.head=HEAD
        self.allowed=True
    def fetch(self,url,*,host):
        self.calls.append((url,host))
        if host=='pypi.org':return {'info':{'name':'ruff','version':'1.0.0'},'urls':[{'digests':{'sha256':'b'*64}}]}
        if host=='registry.npmjs.org':return {'name':'motion','dist-tags':{'latest':'14.9.0'},'versions':{'14.9.0':{}}}
        return {'data':[{'id':'Newtonsoft.Json','version':'13.0.3'}]}
    def run_probe(self,queries,**overrides):
        args={'source_head':HEAD,'current_head':lambda:self.head,
              'authorize':lambda s,a:self.allowed and a=='worm.official_catalog.read',
              'native_stop':lambda:self.stopped,'fetch_json':self.fetch}
        args.update(overrides)
        return probe_official_catalog('owner',queries,**args)
    def test_three_official_providers_pin_hosts_and_preserve_review(self):
        r=self.run_probe([('pypi','ruff'),('npm','motion'),('nuget','Newtonsoft.Json')])
        self.assertEqual(len(r['candidates']),3)
        self.assertEqual([x['license'] for x in r['candidates']],['REVIEW_REQUIRED']*3)
        self.assertFalse(r['models_installed']);self.assertFalse(r['code_executed'])
        self.assertEqual([x[1] for x in self.calls],['pypi.org','registry.npmjs.org','api-v2v3search-0.nuget.org'])
    def test_no_native_grant_blocks_before_network(self):
        self.allowed=False
        with self.assertRaisesRegex(WormHold,'STOP_GRANT_OR_HEAD_CHANGED'): self.run_probe([('pypi','ruff')])
        self.assertEqual(self.calls,[])
    def test_native_stop_blocks_before_network(self):
        self.stopped=True
        with self.assertRaises(WormHold):self.run_probe([('pypi','ruff')])
        self.assertEqual(self.calls,[])
    def test_stop_after_fetch_discard(self):
        def cut(url,*,host):
            value=self.fetch(url,host=host);self.stopped=True;return value
        with self.assertRaises(WormHold):self.run_probe([('pypi','ruff')],fetch_json=cut)
    def test_head_drift_discards(self):
        def drift(url,*,host):
            value=self.fetch(url,host=host);self.head='c'*40;return value
        with self.assertRaises(WormHold):self.run_probe([('pypi','ruff')],fetch_json=drift)
    def test_unapproved_sources_rejected(self):
        for queries in ([('gitlab','x')],[('npm','../x')],[('pypi','x?u')]):
            with self.subTest(q=queries),self.assertRaises(WormHold):self.run_probe(queries)
        self.assertEqual(self.calls,[])
    def test_not_trusting_catalog_license(self):
        x=self.run_probe([('pypi','ruff')])['candidates'][0]
        self.assertEqual(x['sha256_metadata_unverified'],'b'*64)
        self.assertFalse(x['installed']);self.assertFalse(x['imported'])
    def test_wrong_package_id_fails(self):
        with self.assertRaisesRegex(WormHold,'IDENTITY_MISMATCH'):
            self.run_probe([('pypi','ruff')],fetch_json=lambda *_a,**_k:{'info':{'name':'other','version':'1'}})
    def test_invalid_metadata_never_fabricates_version(self):
        with self.assertRaises(WormHold):
            self.run_probe([('npm','motion')],fetch_json=lambda *_a,**_k:{'name':'motion','dist-tags':{},'versions':{}})
    def test_duplicate_query_uses_one_request(self):
        r=self.run_probe([('pypi','ruff'),('pypi','ruff')]);self.assertEqual(r['network_calls'],1)
        self.assertEqual(len(self.calls),1)
    def test_missing_ports_hold(self):
        with self.assertRaisesRegex(WormHold,'EXISTING_NATIVE_PORTS_REQUIRED'):
            self.run_probe([('pypi','ruff')],fetch_json=None)
if __name__=='__main__':unittest.main()
