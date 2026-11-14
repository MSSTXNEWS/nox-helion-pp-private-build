"""Existing A6 isolated-diff UI expansion and reviewed raster receipts."""
import hashlib
import struct
import unittest
from src.nox_selfbuilder.growth_sandbox import (
    make_reviewed_ui_asset_candidate, make_growth_diff)
from src.nox_selfbuilder.worms import WormHold

HEAD='a'*40
def png():
    # Bounded PNG header; this tests source gates, NOT image decoding.
    return b'\\x89PNG\\r\\n\\x1a\\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',512,512)+bytes([8,6,0,0,0])+b'0'*40

class UiSelfGrowth(unittest.TestCase):
    def source(self, data, **extra):
        return {'schema':'NOX-UI-REVIEWED-ASSET-v1','name':'new-nebula.png',
                'media_type':'image/png','sha256':hashlib.sha256(data).hexdigest(),
                'rights_receipt_id':'RIGHTS-AUTH-2026',
                'provenance':'OFFICIAL_OPEN_SOURCE','native_rights_verified':True,
                'derivative_use_approved':True,**extra}
    def stage(self, source, data, **callbacks):
        return make_reviewed_ui_asset_candidate(source,data,session='owner',
             source_head=HEAD,current_head=callbacks.get('head',lambda:HEAD),
             native_authorize=callbacks.get('approve',lambda *_:True),
             stop_requested=callbacks.get('stop',lambda:False))
    def test_existing_wow_graphics_can_be_staged_without_overwrite(self):
        data=png()
        result=self.stage(self.source(data),data)
        self.assertEqual(result['state'],'SANDBOX_ASSET_ONLY')
        self.assertTrue(result['path'].startswith('integrations/wow200/runtime/reviewed/'))
        self.assertFalse(result['original_d02_overwritten'])
        self.assertFalse(result['production_merged'])
    def test_invalid_license_sha_and_stop_fail_closed(self):
        data=png()
        for change in ({'native_rights_verified':False},
                       {'sha256':'f'*64}, {'name':'../../main.js'},
                       {'provenance':'RANDOM_WEB'}):
            with self.subTest(change=change),self.assertRaises(WormHold):
                self.stage(self.source(data,**change),data)
        with self.assertRaises(WormHold):
            self.stage(self.source(data),data,stop=lambda:True)
        with self.assertRaises(WormHold):
            self.stage(self.source(data),data,head=lambda:'b'*40)
        with self.assertRaises(WormHold):
            self.stage(self.source(data),data,approve=lambda *_:False)
    def test_scriptable_svg_cannot_be_admitted_as_graphics(self):
        data=b'<svg onload="alert(1)">'+b'a'*40
        with self.assertRaises(WormHold):
            self.stage(self.source(data,name='evil.svg',media_type='image/svg+xml'),data)
    def test_ui_source_diff_allows_original_menu_wow_and_cinema(self):
        pre='export const title = "NOX";\\n'
        post='export const title = "NOX WOW";\\n'
        def gitblob(raw):
            b=raw.encode('utf-8')
            return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\\0'+b).hexdigest()
        for path in ('ui/onehost-menu-bindings.mjs',
                     'integrations/wow200/runtime/home-scene.mjs',
                     'integrations/creative/web/theater.js'):
            candidate={'schema':'NOX-GROWTH-CANDIDATE-v1',
                       'source_head':HEAD,'candidate_sha256':'f'*64,
                       'candidate_id':'candidate-alpha'}
            receipt={'source_head':HEAD,'path':path,'regular_file':True,
                     'snapshot_verified':True,'pre_blob_sha1':gitblob(pre),
                     'pre_sha256':hashlib.sha256(pre.encode()).hexdigest()}
            ticket=make_growth_diff(candidate,path=path,old_source=pre,new_source=post,
                   source_head=HEAD,source_receipt=receipt,session='owner',
                   native_registry_verify=lambda *_:True,stop_requested=lambda:False)
            self.assertEqual(ticket['state'],'SANDBOX_INPUT_ONLY')
            self.assertFalse(ticket['production_merged'])
if __name__=='__main__': unittest.main()
