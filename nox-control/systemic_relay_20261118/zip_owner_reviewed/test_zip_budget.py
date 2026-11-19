"""Offline proof of bounded ZIP handling; no live NOX or persistent IO."""
import importlib.util
from pathlib import Path
import stat
import unittest
from zipfile import ZipInfo

TARGET=Path(__file__).with_name("merge_web_source.py")
spec=importlib.util.spec_from_file_location("reviewed_zip_merge",TARGET)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def info(name, size=20, compressed=10, file_kind=stat.S_IFREG):
    row=ZipInfo(name)
    row.create_system=3
    row.external_attr=(file_kind|0o644)<<16
    row.file_size=size
    row.compress_size=compressed
    return row


class ZipBudgetTests(unittest.TestCase):
    def test_valid_archive_keeps_exact_count_and_budget(self):
        self.assertEqual(m._zip_budget([info('assets/ok.txt')],0,0),(1,20))
        self.assertEqual(m._zip_budget([info('dir/')],1,20),(2,40))

    def test_bounded_total_before_writing(self):
        with self.assertRaisesRegex(ValueError,'uncompressed byte budget'):
            m._zip_budget([info('x',m.MAX_ZIP_TOTAL_UNCOMPRESSED+1,1000000)],0,0)

    def test_single_member_oversize(self):
        with self.assertRaisesRegex(ValueError,'uncompressed byte budget'):
            m._zip_budget([info('x',m.MAX_ZIP_SINGLE_UNCOMPRESSED+1,1000000)],0,0)

    def test_member_count_and_duplicates(self):
        with self.assertRaisesRegex(ValueError,'entry budget'):
            m._zip_budget([info('x')],m.MAX_ZIP_ENTRIES,0)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            m._zip_budget([info('x'),info('x')],0,0)

    def test_symlink_blocked(self):
        with self.assertRaisesRegex(ValueError,'member kind'):
            m._zip_budget([info('link',4,4,stat.S_IFLNK)],0,0)

    def test_traversal_and_path_aliases_blocked(self):
        for name in ('../escape','dir//alias','C:/evil','/absolute','foo\\bar'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,'Unsafe source path'):
                m._zip_budget([info(name)],0,0)

    def test_ratio_rejected(self):
        with self.assertRaisesRegex(ValueError,'ratio'):
            m._zip_budget([info('small.txt',m.MAX_ZIP_RATIO+1,1)],0,0)


if __name__=="__main__":
    unittest.main()
