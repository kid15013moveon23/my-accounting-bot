"""X25519 + HKDF-SHA256 + AES-256-GCM report envelopes.

The runner derives a domain-separated private key from its existing high-entropy
Telegram bot secret. Only the public key is published; producers never see the
bot token. Rotation of TG_TOKEN intentionally invalidates the old recipient key.
"""
import base64
import hashlib
import json
import os
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DOMAIN=b'coo-live-delivery-v1:kid15013moveon23/my-accounting-bot'
def b64(data):return base64.b64encode(data).decode('ascii')
def unb64(data):return base64.b64decode(data,validate=True)
def raw_public(key):return key.public_bytes(Encoding.Raw,PublicFormat.Raw)
def private_key(token):return X25519PrivateKey.from_private_bytes(hashlib.sha256(DOMAIN+b'\0'+token.strip().encode()).digest())
def recipient(token):
    pub=raw_public(private_key(token).public_key())
    return {'version':1,'public_key':b64(pub),'kid':hashlib.sha256(pub).hexdigest()[:24]}
def key_for(shared,salt):return HKDF(algorithm=hashes.SHA256(),length=32,salt=salt,info=DOMAIN).derive(shared)
def seal(payload,public_config,report_id):
    pub=unb64(public_config['public_key'])
    if public_config['kid']!=hashlib.sha256(pub).hexdigest()[:24]:raise ValueError('Recipient public key fingerprint mismatch')
    ephemeral=X25519PrivateKey.generate()
    salt,nonce=os.urandom(32),os.urandom(12)
    metadata={'version':1,'kid':public_config['kid'],'report_id':report_id}
    aad=json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()
    plaintext=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    if len(plaintext)>200000:raise ValueError('Report too large; shorten or split cards')
    ciphertext=AESGCM(key_for(ephemeral.exchange(X25519PublicKey.from_public_bytes(pub)),salt)).encrypt(nonce,plaintext,aad)
    return dict(metadata,ephemeral_key=b64(raw_public(ephemeral.public_key())),salt=b64(salt),nonce=b64(nonce),ciphertext=b64(ciphertext))
def unseal(envelope,token):
    if envelope['version']!=1 or envelope['kid']!=recipient(token)['kid']:raise ValueError('Recipient key changed; refresh public configuration')
    if len(envelope['ciphertext'])>300000:raise ValueError('Envelope too large')
    metadata={k:envelope[k] for k in ('version','kid','report_id')}
    aad=json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()
    shared=private_key(token).exchange(X25519PublicKey.from_public_bytes(unb64(envelope['ephemeral_key'])))
    data=AESGCM(key_for(shared,unb64(envelope['salt']))).decrypt(unb64(envelope['nonce']),unb64(envelope['ciphertext']),aad)
    return json.loads(data)

if __name__=='__main__':
    import sys
    from pathlib import Path
    if len(sys.argv)!=5:raise SystemExit('Usage: crypto_transport.py DATA.json RECIPIENT.json REPORT_ID OUTPUT.json')
    data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    public=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
    Path(sys.argv[4]).write_text(json.dumps(seal(data,public,sys.argv[3])),encoding='utf-8')
