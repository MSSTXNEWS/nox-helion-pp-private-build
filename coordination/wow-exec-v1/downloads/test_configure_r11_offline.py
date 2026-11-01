import hashlib,importlib.util,json,os,pathlib,shutil,tempfile,unittest
from pathlib import Path
p=Path(__file__).with_name('configure_r11_offline.py')
spec=importlib.util.spec_from_file_location('offline',p)
off=importlib.util.module_from_spec(spec);spec.loader.exec_module(off)
class Offline(unittest.TestCase):
 def test_manifest_count_and_no_autorun(self):
  m=off.lock_manifest(p.with_name(off.LOCK_NAME));self.assertTrue(m['no_autorun']);self.assertEqual(len(m['files']),27)
 def test_checked_real_physical_cache(self):
  cache=os.getenv('NOX_R11_VERIFIED_CACHE')
  if not cache:self.skipTest('NOX_R11_VERIFIED_CACHE not supplied; SHA fixture cannot be invented')
  archive=os.getenv('NOX_R11_NPM_ARCHIVE')
  m=off.lock_manifest(p.with_name(off.LOCK_NAME));self.assertEqual(len(off.verify(Path(cache),m,Path(archive) if archive else None)),27)
 def test_path_escape_and_symlink(self):
  for rel in ['../danger','/root','a/../../b','a\\b']:
   with self.assertRaises(off.UnsafeSource):off.safe_under(Path('/tmp'),rel)
 def test_bad_hash_rejected_without_output(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);cache=root/'cache';cache.mkdir();(cache/'a').write_text('bad')
   lock={'files':[{'path':'a','size':3,'sha256':'a'*64,'kind':'fluent_icon'}]}
   with self.assertRaises(off.UnsafeSource):off.provision(cache,lock,root/'out')
   self.assertFalse((root/'out').exists())
 def test_output_existing_is_no_loss(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);out=root/'out';out.mkdir();(out/'owned.txt').write_text('PRESERVED')
   with self.assertRaises(off.UnsafeSource):off.provision(root,{'files':[]},out)
   self.assertEqual((out/'owned.txt').read_text(),'PRESERVED')
 def test_offline_provision_16_nuget_6_icons_and_npm(self):
  cache=os.getenv('NOX_R11_VERIFIED_CACHE');archive=os.getenv('NOX_R11_NPM_ARCHIVE')
  if not cache or not archive:self.skipTest('Physical cache+archive not supplied; no simulated integration')
  lock=off.lock_manifest(p.with_name(off.LOCK_NAME))
  with tempfile.TemporaryDirectory() as t:
   out=Path(t)/'prepared'
   r=off.provision(Path(cache),lock,out,Path(archive))
   self.assertEqual(r['source_count'],27);self.assertEqual(r['local_nuget_count'],16);self.assertEqual(len(list((out/'nuget-feed').glob('*.nupkg'))),16)
   self.assertTrue((out/'ui-fluent/search.svg').is_file());self.assertTrue((out/'npm-cache/node_modules/motion/package.json').is_file())
   self.assertFalse(r['installed_onehost']);self.assertFalse(r['windows_installers_executed']);self.assertEqual(r['runtime_js_engines_activated'],[])
   import xml.etree.ElementTree as ET
   u=ET.parse(out/'NuGet.Config').getroot();self.assertEqual(u.find('packageSources/add').attrib['key'],'NOX_R11_PINNED_LOCAL')
if __name__=='__main__':unittest.main()
