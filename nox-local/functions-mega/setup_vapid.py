"""Create local-only VAPID credentials, only when user explicitly executes enable-push command."""
import json,base64,sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
D=Path(__file__).resolve().parent
p=D/'nox_connections.json';key=D/'vapid_private.pem'
c={}
if p.exists():
 try:c=json.loads(p.read_text('utf-8'))
 except (OSError,ValueError):raise SystemExit('Invalid NOX config; file preserved')
if c.get('vapid_private_key') and c.get('vapid_public_key'):
 print('Existing VAPID credentials preserved');sys.exit(0)
if key.exists():raise SystemExit('Existing VAPID key present; check manually, no overwrite')
a=ec.generate_private_key(ec.SECP256R1())
pem=a.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
key.write_bytes(pem)
public=a.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
c.update(vapid_private_key=str(key),vapid_public_key=base64.urlsafe_b64encode(public).decode().rstrip('='),vapid_subject='https://localhost')
p.write_text(json.dumps(c,ensure_ascii=False,indent=2),'utf-8')
print('Local VAPID keys created; keep private PEM and nox_connections.json on this PC only')