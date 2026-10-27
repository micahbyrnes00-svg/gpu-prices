"""Minimal WebAuthn (passkey / Face ID) for confirming power actions. ES256 only, attestation 'none'."""
import base64
import hashlib
import json
import os
import secrets
import struct
import time
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

import store

_challenges = {}  # challenge -> expiry
_unlocks = {}     # token -> expiry
UNLOCK_SECONDS = 300


def b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def b64u_dec(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def cbor(data, i=0):
    """Tiny CBOR decoder: enough for WebAuthn attestationObject and COSE keys."""
    ib = data[i]; mt, ai = ib >> 5, ib & 31; i += 1
    if ai < 24: val = ai
    elif ai == 24: val = data[i]; i += 1
    elif ai == 25: val = struct.unpack(">H", data[i:i + 2])[0]; i += 2
    elif ai == 26: val = struct.unpack(">I", data[i:i + 4])[0]; i += 4
    elif ai == 27: val = struct.unpack(">Q", data[i:i + 8])[0]; i += 8
    else: raise ValueError("indefinite CBOR not supported")
    if mt == 0: return val, i
    if mt == 1: return -1 - val, i
    if mt == 2: return data[i:i + val], i + val
    if mt == 3: return data[i:i + val].decode(), i + val
    if mt == 4:
        out = []
        for _ in range(val):
            v, i = cbor(data, i); out.append(v)
        return out, i
    if mt == 5:
        out = {}
        for _ in range(val):
            k, i = cbor(data, i); v, i = cbor(data, i); out[k] = v
        return out, i
    if mt == 7: return {20: False, 21: True, 22: None}.get(ai, val), i
    raise ValueError("unsupported CBOR type")


def new_challenge():
    now = time.time()
    for c in [c for c, t in _challenges.items() if t < now]:
        _challenges.pop(c, None)
    c = b64u(os.urandom(32))
    _challenges[c] = now + 300
    return c


def _check_client(client_json_b64, typ, rp_id):
    cd = json.loads(b64u_dec(client_json_b64))
    if cd.get("type") != typ:
        raise ValueError("wrong ceremony type")
    if _challenges.pop(cd.get("challenge"), 0) < time.time():
        raise ValueError("challenge expired or unknown")
    o = urlparse(cd.get("origin", ""))
    if o.scheme != "https" or o.hostname != rp_id:
        raise ValueError(f"origin mismatch {cd.get('origin')}")
    return b64u_dec(client_json_b64)


def _auth_flags(auth, rp_id):
    if auth[:32] != hashlib.sha256(rp_id.encode()).digest():
        raise ValueError("rpId mismatch")
    flags = auth[32]
    if not (flags & 0x01 and flags & 0x04):
        raise ValueError("user presence + Face ID/Touch ID verification required")
    return flags, struct.unpack(">I", auth[33:37])[0]


def register(body, rp_id, origin):
    _check_client(body["clientDataJSON"], "webauthn.create", rp_id)
    att, _ = cbor(b64u_dec(body["attestationObject"]))
    auth = att["authData"]
    flags, count = _auth_flags(auth, rp_id)
    if not flags & 0x40:
        raise ValueError("no credential data")
    i = 37 + 16
    clen = struct.unpack(">H", auth[i:i + 2])[0]; i += 2
    cred_id = auth[i:i + clen]; i += clen
    cose, _ = cbor(auth, i)
    if cose.get(3) != -7:
        raise ValueError("only ES256 passkeys supported")
    store.x("INSERT OR REPLACE INTO passkeys VALUES (?,?,?,?,?)",
            (b64u(cred_id), b64u(cose[-2]), b64u(cose[-3]), count, time.time()))
    return True


def verify(body, rp_id, origin):
    client = _check_client(body["clientDataJSON"], "webauthn.get", rp_id)
    row = store.q("SELECT * FROM passkeys WHERE cred_id=?", (body["id"],))
    if not row:
        raise ValueError("unknown passkey")
    row = row[0]
    auth = b64u_dec(body["authenticatorData"])
    _, count = _auth_flags(auth, rp_id)
    x, y = b64u_dec(row["x"]), b64u_dec(row["y"])
    pub = ec.EllipticCurvePublicNumbers(int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()).public_key()
    try:
        pub.verify(b64u_dec(body["signature"]), auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as e:
        raise ValueError("bad signature") from e
    store.x("UPDATE passkeys SET sign_count=? WHERE cred_id=?", (count, row["cred_id"]))
    token = secrets.token_urlsafe(24)
    _unlocks[token] = time.time() + UNLOCK_SECONDS
    return token


def unlocked(token):
    return bool(token) and _unlocks.get(token, 0) > time.time()


def enrolled():
    return [{"id": r["cred_id"][:10], "created": r["created"]} for r in store.q("SELECT cred_id, created FROM passkeys")]


def credential_ids():
    return [r["cred_id"] for r in store.q("SELECT cred_id FROM passkeys")]
