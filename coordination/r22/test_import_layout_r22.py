import pathlib
import subprocess
import sys
import tempfile
import unittest

SOURCE=pathlib.Path(__file__).resolve().parent
class ImportLayout(unittest.TestCase):
 def test_git_sibling_directory_layout(self):
  with tempfile.TemporaryDirectory() as root:
   base=pathlib.Path(root)/'coordination'
   a=base/'r21';b=base/'r22';a.mkdir(parents=True);b.mkdir()
   (a/'flow_r21.py').write_bytes((SOURCE/'flow_r21.py').read_bytes())
   (b/'flow_r22.py').write_bytes((SOURCE/'flow_r22.py').read_bytes())
   q=subprocess.run([sys.executable,str(b/'flow_r22.py'),'--help'],
                    cwd=root,capture_output=True,text=True,timeout=8)
   self.assertEqual(q.returncode,0,q.stderr)
   self.assertIn('--registry-blob',q.stdout)
if __name__=='__main__':unittest.main()