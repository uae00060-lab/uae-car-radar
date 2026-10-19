"""Encrypted files in the public repo.

Format (JSON): {"v": 1, "kdf": "pbkdf2-sha256", "iter": N, "salt": b64, "iv": b64, "ct": b64}
AES-256-GCM with a key from PBKDF2-SHA256 of the passphrase. The dashboard decrypts the
same files with the browser's WebCrypto, so both sides must keep this format.
"""

import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITER = 250_000
_keys = {}
# New files reuse the salt of the last file opened with the same passphrase. Each file still gets a
# fresh random IV, so AES-GCM stays safe, while the dashboard server (about 10 ms of CPU per request on
# the free plan) derives one key per passphrase instead of one 250,000-round PBKDF2 per file.
_salts = {}


class BadPassphrase(Exception):
    pass


def _key(passphrase, salt, iters):
    k = (passphrase, salt, iters)
    if k not in _keys:
        _keys[k] = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iters).derive(passphrase.encode())
    return _keys[k]


def encrypt_bytes(data, passphrase):
    salt, iv = _salts.get(passphrase) or os.urandom(16), os.urandom(12)
    _salts[passphrase] = salt
    ct = AESGCM(_key(passphrase, salt, ITER)).encrypt(iv, data, None)
    b = lambda x: base64.b64encode(x).decode()
    return json.dumps({"v": 1, "kdf": "pbkdf2-sha256", "iter": ITER, "salt": b(salt), "iv": b(iv), "ct": b(ct)})


def decrypt_bytes(text, passphrase):
    env = json.loads(text)
    d = base64.b64decode
    try:
        plain = AESGCM(_key(passphrase, d(env["salt"]), int(env["iter"]))).decrypt(d(env["iv"]), d(env["ct"]), None)
    except Exception as e:  # cryptography raises InvalidTag for a wrong passphrase
        raise BadPassphrase("wrong passphrase or damaged file") from e
    if int(env["iter"]) == ITER:
        _salts.setdefault(passphrase, d(env["salt"]))
    return plain


def shared_salt(passphrase):
    salt = _salts.get(passphrase)
    return base64.b64encode(salt).decode() if salt else None


def rekey(path, passphrase):
    """Re-encrypt a file sealed with another salt onto the shared one; True when it was rewritten."""
    with open(path) as f:
        text = f.read()
    target = shared_salt(passphrase)
    if not target or json.loads(text).get("salt") == target:
        return False
    write_file(path, decrypt_bytes(text, passphrase), passphrase)
    return True


def read_json(path, passphrase, default):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.loads(decrypt_bytes(f.read(), passphrase))


def write_json(path, obj, passphrase):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(encrypt_bytes(data, passphrase))
    os.replace(tmp, path)


def write_file(path, data, passphrase):
    with open(path, "w") as f:
        f.write(encrypt_bytes(data, passphrase))
