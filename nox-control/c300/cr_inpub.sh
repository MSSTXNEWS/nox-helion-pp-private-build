echo "K1: cr_inpub (public key only)"
openssl pkey -in /workspace/nox/state/keys/inbox.pem -pubout 2>&1 | head -12
echo END
