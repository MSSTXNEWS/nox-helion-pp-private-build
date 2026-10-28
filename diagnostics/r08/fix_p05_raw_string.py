#!/usr/bin/env python3
"""NOX R08 temporary diagnostic-only C# syntax repair; never edits source ZIP."""
import difflib
import hashlib
import pathlib
import sys

SOURCE_PATH = 'Packages/P05/InstallerRunReport.cs'
EXPECTED_SHA256 = '7a3056d025aeedc3117e5245ac9f84fe76ea4d4afd75e9d9570b31cbfc4e1c1d'
START = '        return """<!doctype html>'
END = '</main></body></html>""";'

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main(root: pathlib.Path) -> None:
    target = root / SOURCE_PATH
    original_bytes = target.read_bytes()
    if sha(original_bytes) != EXPECTED_SHA256:
        raise RuntimeError('HOLD_R08_P05_PREIMAGE_SHA_MISMATCH')
    original = original_bytes.decode('utf-8')
    begin = original.index(START)
    end = original.index(END, begin) + len(END)
    expression = original[begin:end]
    parts = expression.split('"""')
    if len(parts) != 35 or parts[0] != '        return ' or parts[-1] != ';':
        raise RuntimeError('HOLD_R08_P05_RAW_STRING_STRUCTURE_CHANGED')
    fixed = ''.join('@"' + part.replace('"','""') + '"' if i % 2 else part
                    for i,part in enumerate(parts))
    updated = original[:begin] + fixed + original[end:]
    target.write_bytes(updated.encode('utf-8'))
    patch = ''.join(difflib.unified_diff(original.splitlines(keepends=True),
                  updated.splitlines(keepends=True),
                  fromfile='a/R11/'+SOURCE_PATH, tofile='b/R11/'+SOURCE_PATH))
    patch_path = root.parent / 'r08-p05-diagnostic-fix.patch'
    patch_path.write_text(patch, encoding='utf-8')
    receipt_path = root.parent / 'r08-p05-diagnostic-fix-receipt.txt'
    receipt_path.write_text('owner=E06_REVIEW_REQUIRED\npre_sha256='+sha(original_bytes)+'\npost_sha256='+sha(updated.encode('utf-8'))+'\npatch_sha256='+sha(patch.encode('utf-8'))+'\n', encoding='utf-8')
    print('NOX_R08_P05_EXACT_PREIMAGE_FIX_APPLIED pre='+sha(original_bytes)+' post='+sha(updated.encode('utf-8')))

if __name__ == '__main__':
    if len(sys.argv)!=2: raise SystemExit('Usage: fix_p05_raw_string.py <disposable-R11-directory>')
    main(pathlib.Path(sys.argv[1]))