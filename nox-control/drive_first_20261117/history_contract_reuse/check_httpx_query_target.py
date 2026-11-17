#!/usr/bin/env python3
"""Reproduce O0's source-verified wrapper line locally; no HTTP requests."""
import json
from urllib.parse import parse_qs, urlsplit
import httpx

if httpx.__version__ != '0.28.1':
    raise RuntimeError('LOCAL_HTTPX_VERSION_DIFFERS_FROM_OBSERVED_0_28_1')
path = '/api/ui/memory/dialogs/history'
url = httpx.URL('http://127.0.0.1:18775' + path + '?dialog_id=' + '0' * 32 + '&limit=2')
target = path + (f"?{url.query}" if url.query else "")
broken = parse_qs(urlsplit(target).query, strict_parsing=True)
try:
    int(broken['limit'][0])
    result = 'UNEXPECTED_ACCEPTED'
except ValueError:
    result = 'ValueError'
fixed_target = path + ('?' + url.query.decode('ascii') if url.query else '')
fixed = parse_qs(urlsplit(fixed_target).query, strict_parsing=True)
if result != 'ValueError' or fixed != {'dialog_id': ['0' * 32], 'limit': ['2']}:
    raise AssertionError('Reproduction differs')
print(json.dumps({'status': 'PASS_LOCAL_EXACT_LINE_REPRODUCTION',
                  'httpx_version': httpx.__version__,
                  'url_query_type': type(url.query).__name__,
                  'broken_parameter_names': list(broken),
                  'broken_limit': broken['limit'][0], 'int_result': result,
                  'ascii_decoded_keys': list(fixed), 'ascii_decoded_limit': fixed['limit'][0],
                  'real_network_requests': 0, 'native_calls': 0,
                  'native_fix_installed': False}, indent=2))
