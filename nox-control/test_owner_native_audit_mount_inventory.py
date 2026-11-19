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
    def test_remote_filesystems_keep_type_but_skip_statvfs(self):
        for filesystem in ('nfs','fuse.s3fs'):
            calls=[]
            text=f'1 0 0:42 / /data rw - {filesystem} remote rw'
            result=audit._mount_inventory_from_text(text,lambda p:calls.append(p),lambda p:True)
            data=next(x for x in result['storage_paths'] if x['path']=='/data')
            self.assertTrue(data['exists'])
            self.assertEqual(data['filesystem'],filesystem)
            self.assertIsNone(data['total_bytes'])
            self.assertIsNone(data['available_bytes'])
            self.assertEqual(calls,[])
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
class V13OwnerFenceMetadataTests(unittest.TestCase):
    def sample(self, present=(), denied=()):
        seen=[]
        def metadata_only(path):
            name=str(path)
            seen.append(name)
            if any(name.endswith(suffix) for suffix in denied):
                raise PermissionError('not readable')
            if any(name.endswith(suffix) for suffix in present):
                return object()
            raise FileNotFoundError(name)
        observed=audit.v13_owner_fence_metadata(
            root=Path('/fixture/nox'), workspace_stop=Path('/fixture/workspace/NOX_STOP'),
            lstat=metadata_only)
        self.assertEqual(len(seen),11)
        self.assertFalse(observed['may_start_nox'])
        self.assertFalse(observed['may_write_native'])
        self.assertFalse(observed['may_clear_stop'])
        self.assertEqual(observed['owner_lease_state'],'NOT_CHECKED')
        self.assertEqual(observed['scope'],'READ_ONLY_MARKER_METADATA')
        return observed

    def test_no_marker_is_observation_not_owner_clearance(self):
        got=self.sample()
        self.assertEqual(got['owner_stop_state'],'NOT_OBSERVED_NOT_AUTHORIZED')
        self.assertEqual(got['train_hold_state'],'NOT_FOUND_AT_SNAPSHOT')

    def test_present_owner_stop_and_maintenance_always_fence(self):
        for flag in ('/STOP','/state/OWNER_MAINTENANCE.flag','/NOX_STOP'):
            with self.subTest(flag=flag):
                got=self.sample(present=(flag,))
                self.assertEqual(got['owner_stop_state'],'PRESENT')
        got=self.sample(present=('/state/TRAIN_HOLD.flag',))
        self.assertEqual(got['train_hold_state'],'PRESENT')
        self.assertEqual(got['owner_stop_state'],'NOT_OBSERVED_NOT_AUTHORIZED')

    def test_state_stop_flag_independently_fences_and_unreadable_is_unknown(self):
        active = self.sample(present=('/state/STOP.flag',))
        self.assertEqual(active['markers']['STATE_STOP_FLAG'], 'PRESENT')
        self.assertEqual(active['owner_stop_state'], 'PRESENT')
        self.assertEqual(active['markers']['STATE_STOP'], 'NOT_FOUND_AT_SNAPSHOT')
        unreadable = self.sample(denied=('/state/STOP.flag',))
        self.assertEqual(unreadable['markers']['STATE_STOP_FLAG'], 'UNKNOWN_UNREADABLE')
        self.assertEqual(unreadable['owner_stop_state'], 'UNKNOWN')

    def test_unreadable_stop_never_becomes_absent_or_authorized(self):
        got=self.sample(denied=('/state/STOP',))
        self.assertEqual(got['owner_stop_state'],'UNKNOWN')
        self.assertEqual(got['markers']['STATE_STOP'],'UNKNOWN_UNREADABLE')
        got=self.sample(present=('/STOP',),denied=('/state/STOP',))
        self.assertEqual(got['owner_stop_state'],'PRESENT')

    def test_original_supervisor_audit_attaches_fence_without_adding_worker(self):
        from unittest.mock import patch
        with patch.object(audit.shutil, 'which', return_value=None), \
             patch.object(audit.Path, 'is_file', return_value=False), \
             patch.object(audit, 'v13_owner_fence_metadata',
                          return_value={'owner_stop_state':'UNKNOWN'}) as check:
            got=audit.supervisor()
        self.assertIs(got['available'],False)
        self.assertEqual(got['owner_fence_readonly']['owner_stop_state'],'UNKNOWN')
        check.assert_called_once()
        source=SOURCE.read_text()
        self.assertIn('pool.map(worker,range(7))',source)


if __name__=='__main__':unittest.main()

