"""Isolated V61 restore tests. All test data synthetic and non-sensitive."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from nox_runpod.teacher_mesh.v61.restore_offsite_chunks import restore

def _fixture(root:Path):
    parts=[b"encrypted","-","nox","-ciphertext"]
    all_bytes=b"".join(parts)
    digest=hashlib.sha256(all_bytes).hexdigest()
    index={"schema":"NOX_V61_ENCRYPTED_CHUNKS_V1","part_count":4,
           "ciphertext_total_bytes":len(all_bytes),
           "ciphertext_sha256":digest,"parts":[]}
    for i,part in enumerate(parts,1):
        index["parts"].append({"part":i,"file":f"NOX_V61_CIPHER.part{i:02d}",
           "size_bytes":len(part),"sha256":hashlib.sha256(part).hexdigest()})
    for i,part in enumerate(parts,1):
        name=f"NOX_V61_CIPHER.part{i:02d}"
        with zipfile.ZipFile(root/f"NOX_V61_CIPHERTEXT_PART_{i:02d}_20261114.zip","w") as z:
            z.writestr(name,part)
            z.writestr("NOX_V61_CHUNK_INDEX.json",json.dumps(index))
    return all_bytes,digest

class TestOfflineRestore(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir=Path(self.temp.name)
        self.payload,self.sha=_fixture(self.dir)
        self.out=self.dir/"reassembled.age"

    def restored(self):
        return restore(self.dir,self.out,expected_sha=self.sha,
                       expected_bytes=len(self.payload))

    def test_four_part_reassembly(self):
        result=self.restored()
        self.assertEqual(result["state"],"REASSEMBLED_SHA_VERIFIED")
        self.assertEqual(self.out.read_bytes(),self.payload)
        self.assertEqual(result["parts"],4)

    def test_idempotence(self):
        self.restored()
        result=self.restored()
        self.assertEqual(result["state"],"ALREADY_PRESENT_SHA_VERIFIED")

    def test_wrong_existing_output_is_never_overwritten(self):
        self.out.write_bytes(b"KEEP_UNCHANGED")
        with self.assertRaisesRegex(ValueError,"HOLD_OUTPUT_EXISTS_HASH_MISMATCH"):
            self.restored()
        self.assertEqual(self.out.read_bytes(),b"KEEP_UNCHANGED")

    def test_missing_part_cleans_partial(self):
        (self.dir/"NOX_V61_CIPHERTEXT_PART_03_20261114.zip").unlink()
        with self.assertRaisesRegex(ValueError,"HOLD_PART_MISSING"):
            self.restored()
        self.assertFalse(self.out.exists())
        self.assertFalse(list(self.dir.glob(".nox-v61-*.partial")))

    def test_tampered_chunk_detected(self):
        target=self.dir/"NOX_V61_CIPHERTEXT_PART_02_20261114.zip"
        with zipfile.ZipFile(self.dir/"NOX_V61_CIPHERTEXT_PART_01_20261114.zip") as good:
            original_index=good.read("NOX_V61_CHUNK_INDEX.json")
        with zipfile.ZipFile(target,"w") as z:
            z.writestr("NOX_V61_CIPHER.part02",b"TAMPERED")
            z.writestr("NOX_V61_CHUNK_INDEX.json",original_index)
        with self.assertRaisesRegex(ValueError,"HOLD_PART_SHA_MISMATCH"):
            self.restored()
        self.assertFalse(self.out.exists())

    def test_wrong_expected_sha_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"HOLD_SOURCE_SHA"):
            restore(self.dir,self.out,expected_sha="0"*64,
                    expected_bytes=len(self.payload))
        self.assertFalse(self.out.exists())

if __name__=="__main__":
    unittest.main()
