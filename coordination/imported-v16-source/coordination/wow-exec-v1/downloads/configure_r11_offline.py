#!/usr/bin/env python3
"""NOX HELION EXPRESS INTEGRATOR R11 offline source dependency configurator.
Never executes a downloaded EXE. Never edits the original OneHost or user directories.
NuGet feed and optional npm cache are isolated under --out. All source bytes SHA pinned.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, stat, tempfile, xml.etree.ElementTree as ET, zipfile
from pathlib import Path, PurePosixPath

LOCK_NAME='NOX_R11_DEPENDENCY_LOCK.json'

class UnsafeSource(ValueError):pass

def sha256(path:Path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def regular_file(path:Path,root:Path):
    if path.is_symlink() or not path.is_file():raise UnsafeSource('NOT_REGULAR_FILE:'+str(path))
    for parent in (path,*path.parents):
        if parent==root.parent:break
        if parent.is_symlink():raise UnsafeSource('SYMLINK_ANCESTOR:'+str(path))
    return True

def safe_under(root:Path,relative:str):
    p=PurePosixPath(relative)
    if not relative or p.is_absolute() or any(i in ('','.', '..') for i in p.parts) or '\\' in relative:
        raise UnsafeSource('UNSAFE_RELATIVE_PATH:'+relative)
    return root.joinpath(*p.parts)

def lock_manifest(path:Path):
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema')!='NOX_R11_OFFLINE_DEPENDENCIES_V1' or data.get('offline_only') is not True or data.get('no_autorun') is not True:
        raise UnsafeSource('R11_LOCK_SCHEMA_HOLD')
    seen=set()
    for item in data.get('files',[]):
        p=item['path']
        safe_under(Path('.'),p)
        if p in seen or not isinstance(item.get('size'),int) or item['size']<0 or not isinstance(item.get('sha256'),str) or len(item['sha256'])!=64:
            raise UnsafeSource('R11_LOCK_ENTRY_HOLD:'+p)
        seen.add(p)
    if len(data['files'])!=27 or len(data.get('source_modules',[]))!=4:
        raise UnsafeSource('R11_LOCK_FILE_COUNT_HOLD')
    return data

def verify(cache:Path,lock:dict,archive:Path|None=None):
    checked=[]
    for item in lock['files']:
        p=safe_under(cache,item['path'])
        regular_file(p,cache)
        if p.stat().st_size!=item['size'] or sha256(p)!=item['sha256']:
            raise UnsafeSource('R11_DEPENDENCY_SHA_HOLD:'+item['path'])
        checked.append(item['path'])
    if archive is not None:
        regular_file(archive,archive.parent)
        spec=lock['source_archive']
        if archive.stat().st_size!=spec['size'] or sha256(archive)!=spec['sha256']:
            raise UnsafeSource('R11_NPM_SOURCE_ARCHIVE_SHA_HOLD')
    return checked

def provision(cache:Path,lock:dict,out:Path,archive:Path|None=None):
    cache=cache.resolve(strict=True)
    if out.exists() or out.is_symlink():raise UnsafeSource('R11_OUTPUT_MUST_NOT_EXIST')
    if out.is_relative_to(cache) or cache.is_relative_to(out):raise UnsafeSource('R11_OUTPUT_SOURCE_INTERSECTION')
    if not out.parent.is_dir() or out.parent.is_symlink():raise UnsafeSource('R11_OUTPUT_PARENT_UNSAFE')
    checked=verify(cache,lock,archive)
    tmp=Path(tempfile.mkdtemp(prefix='nox-r11-',dir=out.parent))
    records=[]
    try:
        feed=tmp/'nuget-feed';feed.mkdir()
        fluent=tmp/'ui-fluent';fluent.mkdir()
        for item in lock['files']:
            path=item['path']
            source=safe_under(cache,path)
            if item['kind']=='nuget':dest=feed/source.name
            elif item['kind'] in ('fluent_icon','license'):dest=fluent/source.name
            else:continue
            if dest.exists():raise UnsafeSource('R11_FILE_COLLISION_HOLD:'+dest.name)
            shutil.copyfile(source,dest)
            if sha256(dest)!=item['sha256']:raise UnsafeSource('R11_POSTCOPY_SHA_HOLD:'+path)
            records.append({'file':path,'staged':str(dest.relative_to(tmp)).replace('\\','/'),'sha256':item['sha256']})
        if len([r for r in records if r['staged'].startswith('nuget-feed/')])!=16:
            raise UnsafeSource('R11_NUGET_16_PACKAGE_HOLD')
        if archive is not None:
            with zipfile.ZipFile(archive) as z:
                selected=tuple(f"npm/node_modules/{x['module']}/" for x in lock['source_modules'])
                # Only pinned namespaces. Never extract archive paths outside the cache.
                source_modules={}
                for x in lock['source_modules']:
                    source_modules[x['module']]=json.loads(z.read(f"npm/node_modules/{x['module']}/package.json"))
                    if source_modules[x['module']]['version']!=x['version']:
                        raise UnsafeSource('R11_NPM_VERSION_DRIFT:'+x['module'])
                for zinfo in z.infolist():
                    p=zinfo.filename
                    if not p.startswith(selected):continue
                    if zinfo.is_dir():continue
                    # zip permission bits: refuse symlinks, device nodes and oversized payload entries.
                    if stat.S_ISLNK((zinfo.external_attr>>16)&0xffff) or zinfo.file_size>40*1024*1024:
                        raise UnsafeSource('R11_NPM_FILE_UNSAFE:'+p)
                    target=safe_under(tmp/'npm-cache',p.replace('npm/','',1))
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(zinfo) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
                for x in lock['source_modules']:
                    if not (tmp/'npm-cache/node_modules'/x['module']/'package.json').is_file():
                        raise UnsafeSource('R11_NPM_MODULE_MISSING:'+x['module'])
        config=ET.Element('configuration')
        sources=ET.SubElement(config,'packageSources')
        ET.SubElement(sources,'clear')
        ET.SubElement(sources,'add',{'key':'NOX_R11_PINNED_LOCAL','value':'./nuget-feed'})
        ET.ElementTree(config).write(tmp/'NuGet.Config',encoding='utf-8',xml_declaration=True)
        receipt={'schema':'NOX_R11_OFFLINE_READY_V1','source_count':len(checked),'local_nuget_count':16,
                 'fluent_icons':6,'npm_source_cache':archive is not None,
                 'windows_installers_executed':False,'installed_onehost':False,
                 'signature_holds':lock['oss_review'], 'staged':records,
                 'installer_sources':[{'path':v['path'],'sha256':v['sha256'],'status':'CACHE_VERIFIED_ONLY'} for v in lock['files'] if v['kind']=='windows_installer'],
                 'runtime_js_engines_activated':[]}
        (tmp/'R11_COMPONENT_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.replace(tmp,out)
        return receipt
    except BaseException:
        shutil.rmtree(tmp,ignore_errors=True)
        raise

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--lock',type=Path,default=Path(__file__).with_name(LOCK_NAME))
    p.add_argument('--npm-archive',type=Path)
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    lock=lock_manifest(args.lock)
    if args.out is None:
        print(json.dumps({'status':'PINNED_SOURCE_PASS','files':len(verify(args.cache,lock,args.npm_archive))}))
    else:
        print(json.dumps(provision(args.cache,lock,args.out,args.npm_archive),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
