"""Selected immutable typed producer; digest is not authority."""
from typed_prefix import freeze_typed_payload

def freeze_release_payload(*args, **kwargs):
    payload, _producer_digest = freeze_typed_payload(*args, **kwargs)
    return payload
