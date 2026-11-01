"""A.1 read-only official source discovery for existing NOX OneHost research.

No second HTTP stack: injected fetch_json MUST use the existing audited A3
fetch_official_json/no-redirect/128 KiB cap. No install, import, code execution,
model pull or release acceptance. Sources supply metadata, not trusted licenses.
"""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import quote

from .worms import WormHold

_NAMES = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')
_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_HEAD = re.compile(r'[0-9a-f]{40}\Z')
MAX_QUERIES = 3
MAX_RESULTS = 4

# Official published metadata endpoints only, no arbitrary URL/host supplied
# by a website, search result, model output, package manifest or user prompt.
OFFICIAL = {
    'pypi': ('pypi.org', 'https://pypi.org/pypi/{name}/json'),
    'npm': ('registry.npmjs.org', 'https://registry.npmjs.org/{name}/latest'),
    'nuget': ('api-v2v3search-0.nuget.org',
              'https://api-v2v3search-0.nuget.org/query?q={name}&take=4&prerelease=false'),
}


def _checked(stop, authorize, session, head, current_head, stop_epoch=None, expected_stop_epoch=None):
    try:
        if (stop() is not False or authorize(session, 'worm.official_catalog.read') is not True
                or current_head() != head or
                (stop_epoch is not None and stop_epoch() != expected_stop_epoch)):
            raise WormHold('A1_CATALOG_STOP_GRANT_OR_HEAD_CHANGED')
    except WormHold:
        raise
    except Exception as exc:
        raise WormHold('A1_CATALOG_NATIVE_PORT_UNAVAILABLE') from exc


def _text(value, maximum=180):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise WormHold('A1_CATALOG_UNTRUSTED_METADATA')
    return value


def _record(registry, name, version, *, sha256=None):
    name = _text(name, 128)
    version = _text(version, 128)
    # A repository's own manifest/license field does not authorize usage.
    if sha256 is not None and (not isinstance(sha256, str) or not _HEX64.fullmatch(sha256)):
        sha256 = None
    stable = json.dumps([registry, name, version], separators=(',', ':'))
    return {'schema': 'NOX-A1-OFFICIAL-PACKAGE-OBSERVATION-v1',
            'source_id': 'catalog:' + hashlib.sha256(stable.encode()).hexdigest()[:32],
            'registry': registry, 'name': name, 'version_candidate': version,
            'sha256_metadata_unverified': sha256,
            'license': 'REVIEW_REQUIRED', 'rights': 'REVIEW_REQUIRED',
            'status': 'SOURCE_OBSERVED_REVIEW_REQUIRED',
            'download_performed': False, 'imported': False, 'installed': False,
            'executable_run': False}


def _parse(registry, name, data):
    if not isinstance(data, dict):
        raise WormHold('A1_CATALOG_OFFICIAL_JSON_REQUIRED')
    if registry == 'pypi':
        info = data.get('info')
        if not isinstance(info, dict) or str(info.get('name', '')).lower() != name.lower():
            raise WormHold('A1_CATALOG_IDENTITY_MISMATCH')
        version = _text(info.get('version'), 128)
        # PyPI metadata SHA is only a candidate; still verify downloaded bytes.
        urls = data.get('urls')
        hashes = [u.get('digests', {}).get('sha256') for u in urls[:8]
                  if isinstance(u, dict) and isinstance(u.get('digests'), dict)] if isinstance(urls, list) else []
        sha = next((h for h in hashes if isinstance(h, str) and _HEX64.fullmatch(h)), None)
        return [_record(registry, info['name'], version, sha256=sha)]
    if registry == 'npm':
        if str(data.get('name', '')).lower() != name.lower():
            raise WormHold('A1_CATALOG_IDENTITY_MISMATCH')
        # /{name}/latest is a small official version document, not the giant
        # all-versions packument (which exceeds the existing A3 128KiB quota).
        if 'version' in data:
            version = _text(data['version'], 128)
        else:
            tags = data.get('dist-tags')
            version = _text(tags.get('latest') if isinstance(tags, dict) else None, 128)
            versions = data.get('versions')
            if not isinstance(versions, dict) or version not in versions:
                raise WormHold('A1_CATALOG_VERSION_MISSING')
        return [_record(registry, data['name'], version)]
    rows = data.get('data')
    if not isinstance(rows, list) or len(rows) > 100:
        raise WormHold('A1_CATALOG_NUGET_RESULT_INVALID')
    results = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            continue
        if row['id'].lower() != name.lower():
            continue
        results.append(_record(registry, row['id'], row.get('version')))
        break
    if not results:
        raise WormHold('A1_CATALOG_NO_EXACT_PACKAGE_MATCH')
    return results


def probe_official_catalog(session, queries, *, source_head, current_head,
                           authorize, native_stop, fetch_json,
                           stop_epoch=None, expected_stop_epoch=None):
    """Owner-approved queries to 3 official catalogs; data-only review receipts.

    fetch_json(url, host=...) is injected from original A3 adapter and must
    enforce exact official HTTPS origin, forbidden redirects and byte quotas.
    """
    if not all(callable(fn) for fn in (authorize, native_stop, current_head, fetch_json)):
        raise WormHold('A1_CATALOG_EXISTING_NATIVE_PORTS_REQUIRED')
    if (stop_epoch is None) != (expected_stop_epoch is None) or (
            stop_epoch is not None and (not callable(stop_epoch) or
                                         type(expected_stop_epoch) is not int or
                                         expected_stop_epoch < 0)):
        raise WormHold('A1_CATALOG_NATIVE_EPOCH_REQUIRED')
    if not isinstance(source_head, str) or not _HEAD.fullmatch(source_head):
        raise WormHold('A1_CATALOG_EXACT_SOURCE_HEAD_REQUIRED')
    if (not isinstance(queries, (tuple, list)) or not 1 <= len(queries) <= MAX_QUERIES
            or any(not isinstance(x, (tuple, list)) or len(x) != 2 for x in queries)):
        raise WormHold('A1_CATALOG_BOUNDED_QUERY_REQUIRED')
    out, seen = [], set()
    for registry, name in queries:
        if registry not in OFFICIAL or not isinstance(name, str) or not _NAMES.fullmatch(name):
            raise WormHold('A1_CATALOG_APPROVED_REGISTRY_NAME_REQUIRED')
        key = (registry, name.lower())
        if key in seen:
            continue
        seen.add(key)
        _checked(native_stop, authorize, session, source_head, current_head,
                 stop_epoch, expected_stop_epoch)
        host, template = OFFICIAL[registry]
        url = template.format(name=quote(name, safe=''))
        try:
            payload = fetch_json(url, host=host)
        except WormHold:
            raise
        except Exception as exc:
            raise WormHold('A1_CATALOG_ORIGINAL_PROVIDER_UNAVAILABLE') from exc
        _checked(native_stop, authorize, session, source_head, current_head,
                 stop_epoch, expected_stop_epoch)
        out.extend(_parse(registry, name, payload))
        if len(out) > MAX_RESULTS:
            raise WormHold('A1_CATALOG_RESULT_LIMIT')
    return {'schema': 'NOX-A1-OFFICIAL-CATALOG-BATCH-v1',
            'source_head': source_head, 'candidates': out,
            'code_executed': False, 'models_installed': False,
            'network_calls': len(seen), 'native_install_approved': False}
