"""Two static UI file projections through the already-owned inspector Reader.

No standalone entry, app import, HTTP, browser, write, source edit or restart.
The caller keeps the existing shared maintenance lease and Reader deadline.
"""
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

SITE = 'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
READSET = ((SITE + '/chat.html', 131072),
           (SITE + '/pc/v25/nox-shell-v25.js', 131072))
MAX_TOTAL_CONTENT_BYTES = 262144
MAX_SCRIPT_PATHS = 48
MAX_SCRIPT_PATH_BYTES = 192
HISTORICAL_SHELL_SHA = '922f824d94a09f08c5b7ab5ed3fc866ca0bbc8bce8260a969f6cca38cdea9343'
PATH_PATTERN = re.compile(r'/?(?:\.{1,2}/)*(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:js|mjs)')


def _script_path(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    # Only local asset paths are disclosed. Query, fragment, credentials,
    # external origins, data/blob URLs and encoded/parameterized paths are withheld.
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path
    if (not path or len(path.encode()) > MAX_SCRIPT_PATH_BYTES
            or PATH_PATTERN.fullmatch(path) is None):
        return None
    return path


class _ScriptSources(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paths = []
        self.source_tags = 0
        self.withheld = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'script':
            return
        values = [value for key, value in attrs if key.lower() == 'src']
        if not values:
            return
        self.source_tags += 1
        path = _script_path(values[0]) if len(values) == 1 else None
        if path is None or len(self.paths) >= MAX_SCRIPT_PATHS:
            self.withheld += 1
        else:
            self.paths.append(path)


def project(reader):
    """Call after reader.acquire()/prepare(); caller owns close() and output."""
    reader.guard()
    result = {'schema': 'NOX_CURRENT_UI_SOURCE_PROJECTION_V1',
              'scope': 'BOUNDED_SERVER_FILES_NOT_RENDERED_UI',
              'files': [], 'content_bytes_read': 0,
              'max_content_bytes': MAX_TOTAL_CONTENT_BYTES,
              'raw_html_or_js_exported': False,
              'actual_visibility_proven': False, 'served_decorated_html_observed': False,
              'query_fragment_or_authority_exported': False,
              'http_calls': 0, 'writes': 0, 'reloads': 0}
    for relative, limit in READSET:
        row = {'path': '/root/nox/' + relative, 'limit_bytes': limit}
        try:
            raw, info = reader.read(relative, limit)
            if not isinstance(raw, bytes) or len(raw) > limit:
                raise ValueError('UI_READER_BOUND')
            result['content_bytes_read'] += len(raw)
            row.update(status='FILE_SHA_OBSERVED', sha256=sha256(raw).hexdigest(),
                       bytes=len(raw), dev=info.st_dev, ino=info.st_ino,
                       uid=info.st_uid, gid=info.st_gid, mode=oct(info.st_mode & 0o7777))
            text = raw.decode('utf-8', errors='strict')
            if relative.endswith('/chat.html'):
                parser = _ScriptSources()
                parser.feed(text)
                parser.close()
                row.update(script_src_paths=parser.paths,
                           script_src_tags=parser.source_tags,
                           script_paths_withheld=parser.withheld,
                           direct_v25_shell_script_included=any(
                               path == 'v25/nox-shell-v25.js' or
                               path.endswith('/v25/nox-shell-v25.js') for path in parser.paths),
                           n25_dock_literal_present='n25-dock' in text)
            else:
                row.update(exact_historical_shell_bytes=(row['sha256'] == HISTORICAL_SHELL_SHA),
                           n25_dock_literal_present='n25-dock' in text,
                           dock_class_assignment_literal_present=(
                               "d.className = 'n25-dock'" in text),
                           legacy_nav_literal_present='function legacyNav()' in text)
        except Exception as error:
            # Optional UI absence cannot relabel a proven worker/queue result.
            # Never include exception messages, file bodies or unparsed attributes.
            row['status'] = 'READ_OR_PROJECTION_UNAVAILABLE'
            row['failure_type'] = type(error).__name__[:64]
        result['files'].append(row)
        reader.check()
    reader.guard()
    result['status'] = ('TWO_CURRENT_FILE_PROJECTIONS_OBSERVED'
                        if all(row['status'] == 'FILE_SHA_OBSERVED' for row in result['files'])
                        else 'PARTIAL_FILE_PROJECTION')
    return result
