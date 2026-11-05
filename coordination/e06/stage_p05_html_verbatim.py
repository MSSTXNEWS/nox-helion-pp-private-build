"""T06 · source-locked P05 HTML raw-literal repair in disposable R11 only.

C# 11 multiline raw strings cannot begin inline with HTML on the same line.
The original P01_C07 archive has 17 invalid HTML raw-string segments within
one return expression. Convert only those segments into equivalent verbatim
C# strings; preserve HTML text, quotations, dynamic expressions, and media.
Never edit the 28-part original donor archive or the 729-file SourceLock.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import sys

START = '        return """<!doctype html>'
END = '</main></body></html>""";'
PATTERN = re.compile(r'"""(.*?)"""', re.DOTALL)
VERBATIM = re.compile(r'@"((?:""|[^"])*)"', re.DOTALL)
EXPECTED_SEGMENTS = 17


def main(source: Path) -> None:
    source = source.resolve(strict=True)
    target = source / "Packages/P05/InstallerRunReport.cs"
    if not target.is_file() or target.is_symlink():
        raise SystemExit("E06_P05_ORIGINAL_SOURCE_MISSING_OR_REPARSE_HOLD")
    node = target
    while node != source:
        if node.is_symlink() or getattr(node, "is_junction", lambda: False)():
            raise SystemExit("E06_P05_REPARSE_ANCESTOR_HOLD")
        if source not in node.parents:
            raise SystemExit("E06_P05_STAGE_ESCAPE_HOLD")
        node = node.parent
    raw = target.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise SystemExit("E06_P05_ORIGINAL_ENCODING_HOLD") from exc
    if text.count(START) != 1 or text.count(END) != 1:
        raise SystemExit("E06_P05_EXACT_ORIGINAL_HTML_ANCHOR_HOLD")
    start = text.index(START)
    end = text.index(END, start) + len(END)
    original = text[start:end]
    matches = list(PATTERN.finditer(original))
    if len(matches) != EXPECTED_SEGMENTS or original.count('"""') != 2 * EXPECTED_SEGMENTS:
        raise SystemExit("E06_P05_RAW_HTML_SEGMENT_COUNT_HOLD")
    rewritten = PATTERN.sub(
        lambda m: '@"' + m.group(1).replace('"', '""') + '"', original)
    # A lossless inverse proves every HTML codepoint, literal quote and
    # untouched C# dynamic expression is byte-identical to the intended text.
    recovered = VERBATIM.sub(
        lambda m: '"""' + m.group(1).replace('""', '"') + '"""', rewritten)
    if recovered != original or '"""' in rewritten:
        raise SystemExit("E06_P05_HTML_INTERPOLATION_NOLOSS_HOLD")
    result = text[:start] + rewritten + text[end:]
    after = (b"\xef\xbb\xbf" if bom else b"") + result.encode("utf-8")
    if raw == after or target.read_bytes() != raw:
        raise SystemExit("E06_P05_CONCURRENT_STAGE_OR_EMPTY_PATCH_HOLD")
    # Only the throwaway R11 copy is mutated, never original ZIP/source parts.
    target.write_bytes(after)
    if target.read_bytes() != after:
        raise SystemExit("E06_P05_STAGE_READBACK_HOLD")
    print("E06_P05_HTML_VERBATIM_NOLOSS_STAGE_PASS",
          EXPECTED_SEGMENTS,
          hashlib.sha256(raw).hexdigest(),
          hashlib.sha256(after).hexdigest(), flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("USAGE: stage_p05_html_verbatim.py DISPOSABLE_R11")
    main(Path(sys.argv[1]))
