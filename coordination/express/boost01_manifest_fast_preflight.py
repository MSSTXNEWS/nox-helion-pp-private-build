#!/usr/bin/env python3
"""NOX EXPRESS BOOST01: bounded, offline metadata and selective byte preflight.

No network, installation, extraction, source rewrite, CI or release promotion.
A passing manifest check is NOT a passing physical cache, license or E07 check.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath

VOLUME_PIN = 'cee32a140122f98592677e6ee68f0e474b3787a2764b5dd08e480b8902af712c'
INDEX_PIN = '50c1c6c78d91529c2a4c78a6c171b83a73604bdfe0943d989ca72086fce78412'
ARCHIVE_SHA = '2ca2647e46edd1e110db1569cb6a636ceee8e8154b416560ad43a87fb95545bd'
D02_SHA = {
    'APPROVED_D02/home.png': '382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a',
    'APPROVED_D02/menu.png': '4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9',
    'APPROVED_D02/core01.png': '343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97',
    'APPROVED_D02/menu_sections.png': '7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4',
}
TOOLS = {
    'R11_READY/official/nsis-3.13-setup.exe': ('db9a1038bbc0e53fef24f423fd609979bd578e942f1be1198db186d1c42652a3',1567985),
    'R11_READY/official/MicrosoftEdgeWebView2RuntimeInstallerX64.exe': ('62863f0f0611a16ccf124b4f15650c3b66624504eba74d7cde1e2ae5d951249b',215017168),
    'WINDOWS_INSTALLERS/OllamaSetup-v0.40.13-x64.exe': ('9e3c76e54e7184c68e88a2378b909bf59bbe454f83c076cb4f4a717e946ae719',1676266440),
}
HEX = re.compile(r'\A[0-9a-f]{64}\Z')

class Hold(ValueError):
    pass

def need(value: bool, label: str) -> None:
    if not value:
        raise Hold(label)

def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()

def plain_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()

def pinned_json(path: Path, digest: str) -> dict:
    need(plain_file(path), 'BOOST01_MANIFEST_FILE_HOLD')
    need(sha_file(path) == digest, 'BOOST01_MANIFEST_PIN_HOLD')
    obj = json.loads(path.read_text(encoding='utf-8'))
    need(type(obj) is dict, 'BOOST01_MANIFEST_SHAPE_HOLD')
    return obj

def relative_path(name: str) -> PurePosixPath:
    need(isinstance(name,str) and name and not name.startswith('/') and '\\' not in name and ':' not in name,
         'BOOST01_UNSAFE_RELATIVE_PATH')
    p=PurePosixPath(name)
    need(all(x not in ('', '.', '..') for x in name.split('/')) and p.as_posix() == name,
         'BOOST01_UNSAFE_RELATIVE_PATH')
    return p

def validate_index(volume: dict, index: dict) -> dict:
    need(volume.get('schema') == 'NOX-MEGA-BOOST-V4-VERIFIED-VOLUMES' and
         index.get('schema') == 'NOX_MEGA_BOOST_LOCAL_V4' and
         index.get('github_pr162_full_tree_included') is False and
         index.get('e07') == 'NOT_VERIFIED', 'BOOST01_SCOPE_HOLD')
    parts=volume.get('parts')
    need(type(parts) is list and len(parts) == 6, 'BOOST01_PARTS_COUNT_HOLD')
    total=0
    for n,item in enumerate(parts,1):
        name=f'NOX_HELION_MEGA_BOOST_MONOLITH_V4.zip.part{n:02d}'
        need(type(item) is dict and item.get('filename') == name and
             type(item.get('bytes')) is int and item['bytes'] > 0 and
             isinstance(item.get('sha256'),str) and HEX.fullmatch(item['sha256']),
             'BOOST01_PART_PIN_SHAPE_HOLD')
        total += item['bytes']
    need(total == 2327776086 and volume.get('archive_size') == total and
         volume.get('archive_sha256') == ARCHIVE_SHA, 'BOOST01_ARCHIVE_CROSSPIN_HOLD')
    items=index.get('items')
    need(type(items) is dict and len(items) >= 3454, 'BOOST01_INDEX_COUNT_HOLD')
    for path,entry in items.items():
        relative_path(path)
        need(type(entry) is dict and type(entry.get('bytes')) is int and
             entry['bytes'] >= 0 and isinstance(entry.get('sha256'),str) and
             HEX.fullmatch(entry['sha256']), 'BOOST01_INDEX_ENTRY_HOLD')
    for name, digest in D02_SHA.items():
        need(name in items and items[name]['sha256'] == digest,
             'BOOST01_D02_PIN_HOLD')
    for name, (digest, size) in TOOLS.items():
        need(name in items and items[name]['sha256'] == digest and
             items[name]['bytes'] == size, 'BOOST01_TOOL_PIN_HOLD')
    nuget={k:v for k,v in items.items() if k.startswith('NUGET_OFFLINE_FEED/') and k.endswith('.nupkg')}
    need(len(nuget) == 16 and volume.get('contents',{}).get('nuget_packages') == 16 and
         volume.get('contents',{}).get('canon_d02_png') == 4 and
         volume.get('contents',{}).get('nsis_setup_3_13') is True,
         'BOOST01_NUGET_OR_D02_COUNT_HOLD')
    return {'status':'MANIFEST_PINS_PASS_ONLY','volume_sha256':VOLUME_PIN,
            'index_sha256':INDEX_PIN,'archive_sha256_claim':ARCHIVE_SHA,
            'six_part_metadata_bytes':total,'nuget_pinned_entries':len(nuget),
            'nuget_metadata_bytes':sum(x['bytes'] for x in nuget.values()),
            'approved_d02_entries':len(D02_SHA),
            'nsis_3_13_entry_pinned':True,'webview2_entry_pinned':True,
            'ollama_0_40_13_entry_pinned':True,
            'python_3_12_10_stager_in_cache':False,
            'python_3_13_2_substitute_allowed':False,
            'nuget_redistribution_licenses_approved':False,
            'quarantined_librehardwaremonitor_allowed':False,
            'ollama_authenticode_proved_from_manifest':False,
            'physical_archive_sha_verified_this_run':False,
            'onehost_executed':False,'release_accepted':False,'e07_pass':False}

def verify_selected(index: dict, root: Path, selected: list[str]) -> list[dict]:
    need(root.is_dir() and not root.is_symlink(), 'BOOST01_CACHE_ROOT_HOLD')
    base=root.resolve(strict=True)
    need(len(set(selected)) == len(selected), 'BOOST01_DUPLICATE_SELECTION_HOLD')
    seen=set()
    results=[]
    for name in selected:
        p=relative_path(name)
        need(name not in seen, 'BOOST01_DUPLICATE_SELECTION_HOLD')
        seen.add(name)
        need(name in index['items'] and not name.startswith('QUARANTINE_UNVERIFIED/'),
             'BOOST01_UNAPPROVED_ASSET_HOLD')
        candidate=base
        for piece in p.parts:
            candidate=candidate/piece
            need(not candidate.is_symlink(), 'BOOST01_SYMLINK_HOLD')
        need(plain_file(candidate) and candidate.resolve(strict=True).is_relative_to(base),
             'BOOST01_SELECTED_FILE_MISSING_HOLD')
        observed=candidate.stat().st_size
        need(observed==index['items'][name]['bytes'], 'BOOST01_SELECTED_SIZE_HOLD')
        need(sha_file(candidate)==index['items'][name]['sha256'], 'BOOST01_SELECTED_SHA_HOLD')
        results.append({'path':name,'sha256':index['items'][name]['sha256'],
                        'bytes':observed,'physical_sha256':'PASS'})
    return results

def check(volume_path: Path, index_path: Path, root: Path | None=None,
          selected: list[str] | None=None, parts_dir: Path | None=None) -> dict:
    vol=pinned_json(volume_path,VOLUME_PIN)
    idx=pinned_json(index_path,INDEX_PIN)
    report=validate_index(vol,idx)
    selected=selected or []
    need(not selected or root is not None, 'BOOST01_CACHE_ROOT_REQUIRED')
    report['local_selected_checks']=verify_selected(idx,root,selected) if selected else []
    report['part_checks']=[]
    if parts_dir is not None:
        need(parts_dir.is_dir() and not parts_dir.is_symlink(), 'BOOST01_PART_ROOT_HOLD')
        for entry in vol['parts']:
            path=parts_dir/entry['filename']
            need(plain_file(path) and path.stat().st_size==entry['bytes'] and
                 sha_file(path)==entry['sha256'], 'BOOST01_PART_SHA_HOLD')
            report['part_checks'].append({'file':entry['filename'],'physical_sha256':'PASS'})
    report['physical_archive_sha_verified_this_run']=False  # per-part hashes != joined ZIP proof
    report['release_accepted']=False  # deliberately fail closed, no license or E07 claim
    return report

def selftest(volume: Path,index:Path) -> int:
    import unittest
    class Checks(unittest.TestCase):
        def test_original_metadata_only(self):
            r=check(volume,index)
            self.assertEqual(r['nuget_pinned_entries'],16)
            self.assertEqual(r['approved_d02_entries'],4)
            self.assertFalse(r['release_accepted'])
            self.assertFalse(r['physical_archive_sha_verified_this_run'])
        def test_tampered_volume_denied(self):
            with tempfile.TemporaryDirectory() as d:
                f=Path(d)/'volume.json';f.write_bytes(volume.read_bytes()+b' ')
                with self.assertRaisesRegex(Hold,'MANIFEST_PIN_HOLD'):check(f,index)
        def test_tampered_index_denied(self):
            with tempfile.TemporaryDirectory() as d:
                f=Path(d)/'index.json';f.write_bytes(index.read_bytes()+b' ')
                with self.assertRaisesRegex(Hold,'MANIFEST_PIN_HOLD'):check(volume,f)
        def test_missing_selection_denied(self):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaisesRegex(Hold,'SELECTED_FILE_MISSING_HOLD'):
                    check(volume,index,Path(d),['APPROVED_D02/home.png'])
        def test_traversal_denied(self):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaisesRegex(Hold,'UNSAFE_RELATIVE_PATH'):
                    check(volume,index,Path(d),['../secret'])
        def test_duplicate_selection_denied(self):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaisesRegex(Hold,'DUPLICATE_SELECTION_HOLD'):
                    check(volume,index,Path(d),['APPROVED_D02/home.png']*2)
        def test_unreviewed_quarantine_denied(self):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaisesRegex(Hold,'UNAPPROVED_ASSET_HOLD'):
                    check(volume,index,Path(d),['QUARANTINE_UNVERIFIED/R11/official/librehardwaremonitorlib.0.9.6.nupkg'])
        def test_local_mismatched_hash_denied(self):
            with tempfile.TemporaryDirectory() as d:
                f=Path(d)/'APPROVED_D02/home.png';f.parent.mkdir();f.write_bytes(b'bad')
                with self.assertRaisesRegex(Hold,'SELECTED_SIZE_HOLD'):
                    check(volume,index,Path(d),['APPROVED_D02/home.png'])
        def test_license_and_runtime_not_promoted(self):
            r=check(volume,index)
            for key in ('nuget_redistribution_licenses_approved','python_3_12_10_stager_in_cache',
                        'ollama_authenticode_proved_from_manifest','e07_pass'):
                self.assertIs(r[key],False)
    result=unittest.TextTestRunner(verbosity=2,stream=sys.stderr).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    return 0 if result.wasSuccessful() else 1

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--volume-manifest',required=True,type=Path)
    p.add_argument('--index-manifest',required=True,type=Path)
    p.add_argument('--cache-root',type=Path)
    p.add_argument('--verify-local',action='append',default=[])
    p.add_argument('--parts-dir',type=Path,help='Opt-in 2.3 GB local hashing; never downloaded')
    p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    if args.self_test: return selftest(args.volume_manifest,args.index_manifest)
    try:
        print(json.dumps(check(args.volume_manifest,args.index_manifest,args.cache_root,
                               args.verify_local,args.parts_dir),ensure_ascii=False,sort_keys=True))
        return 0
    except (Hold,ValueError,OSError,json.JSONDecodeError) as e:
        print(json.dumps({'status':'HOLD','error':str(e),'release_accepted':False,
                          'e07_pass':False},sort_keys=True),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())