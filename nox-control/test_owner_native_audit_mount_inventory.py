import importlib.util
from pathlib import Path
import unittest
SOURCE=Path(__file__).with_name('owner_native_audit.py')
spec=importlib.util.spec_from_file_location('owner_native_audit_under_test',SOURCE)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
class Stat:
    f_frsize=4096
    f_bsize=4096
    f_blocks=100
    f_bavail=25
class MountInventoryTests(unittest.TestCase):
    def setUp(self):
        self.mountinfo='''36 25 8:1 / / rw,relatime - ext4 /dev/sda1 rw
37 36 8:2 / /data\\040volume rw,relatime - xfs /dev/sdb1 rw
38 36 0:42 / /proc rw,nosuid - proc proc rw
39 36 8:3 / /mnt ro,relatime - ext4 /dev/sdc1 ro
'''
    def test_includes_safe_block_mounts_and_decodes_paths(self):
        result=audit._mount_inventory_from_text(self.mountinfo,lambda p:Stat())
        self.assertTrue(result['mountinfo_readable'])
        self.assertEqual([r['mountpoint'] for r in result['mounts']],['/','/data volume','/mnt'])
        self.assertEqual(result['mounts'][0]['available_bytes'],102400)
        self.assertFalse(result['data_mount_present'])
        self.assertEqual(result['eligible_block_mount_count'],3)
        self.assertEqual(result['mountinfo_entry_count'],4)
    def test_exposes_direct_data_mount_without_claiming_provider_disk(self):
        result=audit._mount_inventory_from_text('1 0 8:1 / /data rw - ext4 /dev/sda1 rw',lambda p:Stat())
        self.assertTrue(result['data_mount_present'])
        self.assertEqual(result['provider_disk_visibility'],'not_established')
    def test_omits_pseudofs_and_source_strings(self):
        result=audit._mount_inventory_from_text(self.mountinfo,lambda p:Stat())
        rendered=repr(result)
        self.assertNotIn('/dev/sda1',rendered)
        self.assertNotIn("'filesystem': 'proc'",rendered)
        self.assertIn('device_major_minor',rendered)
    def test_data_path_resolves_underlying_overlay_mount_and_capacity(self):
        text='1 0 0:42 / / rw - overlay overlay rw'
        result=audit._mount_inventory_from_text(text,lambda p:Stat(),lambda p:p in ('/','/data','/workspace'))
        data=next(x for x in result['storage_paths'] if x['path']=='/data')
        self.assertFalse(result['data_mount_present'])
        self.assertTrue(data['exists'])
        self.assertEqual(data['mountpoint'],'/')
        self.assertEqual(data['filesystem'],'overlay')
        self.assertEqual(data['available_bytes'],102400)
    def test_exact_data_overlay_mount_is_reported(self):
        text='1 0 0:42 / /data rw - overlay overlay rw'
        result=audit._mount_inventory_from_text(text,lambda p:Stat(),lambda p:True)
        self.assertTrue(result['data_mount_present'])
        self.assertEqual(result['data_mount_entry']['filesystem'],'overlay')
        self.assertEqual(result['mounts'],[])
    def test_stat_failure_is_reported_as_unknown_capacity(self):
        result=audit._mount_inventory_from_text('1 0 8:1 / /data rw - ext4 /dev/x rw',
                                                 lambda p:(_ for _ in ()).throw(OSError()))
        self.assertIsNone(result['mounts'][0]['total_bytes'])
        self.assertTrue(result['data_mount_present'])
    def test_malformed_rows_are_ignored(self):
        result=audit._mount_inventory_from_text('broken\n1 0 nope / /data rw - ext4 /dev/x rw',lambda p:Stat())
        self.assertEqual(result['mounts'],[])
    def test_input_is_bounded(self):
        rows=['1 0 8:1 / / rw - ext4 /dev/sda rw']+['x']*4096
        result=audit._mount_inventory_from_text('\n'.join(rows),lambda p:Stat())
        self.assertTrue(result['truncated'])
    def test_worker_dispatch_includes_mount_inventory(self):
        original=audit.mount_inventory
        try:
            def fake_mount_inventory(): return {'mountinfo_readable':True,'mounts':[]}
            fake_mount_inventory.__name__='mount_inventory'
            audit.mount_inventory=fake_mount_inventory
            row=audit.worker(6)
        finally:
            audit.mount_inventory=original
        self.assertEqual(row['section'],'mount_inventory')
        self.assertEqual(row['result']['mountinfo_readable'],True)
        source=SOURCE.read_text()
        self.assertIn('pool.map(worker,range(7))',source)
    def test_source_is_safe_read_only_probe(self):
        names=audit.mount_inventory.__code__.co_names
        self.assertFalse(any(word in names for word in ('unlink','remove','Popen')))
        self.assertIn('/proc/self/mountinfo',audit.mount_inventory.__code__.co_consts)
if __name__=='__main__':unittest.main()

