"""Separate Python namespace for the exact B5 R80 producer.
The returned digest is deliberately not exposed as admission authority.
Caller must supply original retained descriptors and authenticated link pins.
"""
from frozen_consumer import freeze_consumer_payload

def freeze_release_payload(*args, **kwargs):
    raw, _producer_digest = freeze_consumer_payload(*args, **kwargs)
    return raw
