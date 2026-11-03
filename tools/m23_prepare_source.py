#!/usr/bin/env python3
"""Assemble frozen PRE-PRE source and apply the M2.3 persona/STOP overlay.

Does not modify source_*.part, the pinned private_build.ps1 hashes, or the
reference EXE sha256 93a329ba1ece9cfd66951b377e04e9c1166ec6ba3ce13a5911ba8e36de99dfb8.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

SOURCE_SHA = 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a'
SOURCE_BYTES = 60364346
REFERENCE_EXE_SHA = '93a329ba1ece9cfd66951b377e04e9c1166ec6ba3ce13a5911ba8e36de99dfb8'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(cmd: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if completed.returncode != 0:
        raise SystemExit(
            'command failed: ' + ' '.join(cmd) + '\n' + completed.stdout + completed.stderr)


def apply_patch(source: Path, patch: Path) -> None:
    run(['git', 'apply', '--whitespace=nowarn', '--check', str(patch)], cwd=source)
    run(['git', 'apply', '--whitespace=nowarn', str(patch)], cwd=source)


def prepare(repo: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    work = dest.parent / (dest.name + '-staging')
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    archive = work / 'NOX_PP_SOURCE.zip'
    with archive.open('wb') as out:
        for name in ('source_00.part', 'source_01.part', 'source_02.part'):
            part = repo / name
            if not part.is_file():
                raise SystemExit('missing ' + name)
            with part.open('rb') as handle:
                shutil.copyfileobj(handle, out)
    if archive.stat().st_size != SOURCE_BYTES or sha256(archive) != SOURCE_SHA:
        raise SystemExit('source archive does not match the frozen PRE-PRE binding')
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(dest)
    delivery = dest / '_delivery'
    if delivery.exists():
        shutil.rmtree(delivery)
    patch_dir = work / 'a04'
    patch_dir.mkdir()
    with zipfile.ZipFile(repo / 'NOX_A04_BUILD_PATCH.zip') as zipped:
        zipped.extractall(patch_dir)
    apply_patch(dest, patch_dir / 'A04_BUILD_REPAIRS_EXACT_PARENT.patch')
    apply_patch(dest, repo / 'PP_MENU_CATALOG_BUNDLE.patch')
    apply_patch(dest, repo / 'PP_FAST_CANDIDATE_MODE.patch')
    apply_patch(dest, repo / 'm23_overlay' / 'M23_SHELL_HOOKS.patch')
    overlay = repo / 'm23_overlay'
    for source_file in (overlay / 'helion').glob('*.py'):
        shutil.copy2(source_file, dest / 'helion' / source_file.name)
    shutil.copy2(overlay / 'tests' / 'test_m23_persona_memory_stop.py',
                 dest / 'tests' / 'test_m23_persona_memory_stop.py')
    shutil.copy2(overlay / 'run_m23_entry.py', dest / 'run_m23_entry.py')
    marker = dest / 'M23_OVERLAY_MARKER.txt'
    marker.write_text(
        'M2.3 persona/memory/STOP overlay applied.\n'
        'reference_exe_sha256=' + REFERENCE_EXE_SHA + '\n'
        'reference_exe_modified=false\n',
        encoding='utf-8')
    shutil.rmtree(work)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Prepare M2.3 source tree')
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--dest', type=Path, required=True)
    args = parser.parse_args(argv)
    prepare(args.repo.resolve(), args.dest.resolve())
    print('M23_SOURCE_READY', args.dest)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
