"""Web Push sender: VAPID (RFC 8292) + aes128gcm payload encryption (RFC 8291).

Needs python3-cryptography (Debian package). No third-party push service; the Pi talks
directly to Apple's push servers (*.push.apple.com) over HTTPS.
"""
import base64
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import store

CONTACT = os.environ.get("PUSH_CONTACT", "mailto:orbit@localhost")


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _hmac(key, data):
    h = hmac.HMAC(key, hashes.SHA256())
    h.update(data)
    return h.finalize()


def _pub_bytes(pub) -> bytes:
    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def vapid_keys():
    """Load or create the server's VAPID key pair (kept in Orbit's state dir)."""
    path = store.STATE / "vapid_private.pem"
    if not path.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
        os.chmod(path, 0o600)
    key = serialization.load_pem_private_key(path.read_bytes(), None)
    return key, b64u(_pub_bytes(key.public_key()))


def _vapid_header(endpoint: str) -> str:
    key, pub = vapid_keys()
    u = urllib.parse.urlparse(endpoint)
    claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": CONTACT}
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    signing = f"{head}.{body}".encode()
    r, s = decode_dss_signature(key.sign(signing, ec.ECDSA(hashes.SHA256())))
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"vapid t={head}.{body}.{b64u(sig)}, k={pub}"


def encrypt(payload: bytes, p256dh: str, auth: str) -> bytes:
    ua_pub = b64u_dec(p256dh)
    auth_secret = b64u_dec(auth)
    as_key = ec.generate_private_key(ec.SECP256R1())
    as_pub = _pub_bytes(as_key.public_key())
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    shared = as_key.exchange(ec.ECDH(), ua_key)
    prk_key = _hmac(auth_secret, shared)
    ikm = _hmac(prk_key, b"WebPush: info\x00" + ua_pub + as_pub + b"\x01")
    salt = os.urandom(16)
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    ct = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack(">I", 4096) + bytes([len(as_pub)]) + as_pub + ct


def send(sub: dict, data: dict, urgency="normal", ttl=86400, topic=None) -> int:
    body = encrypt(json.dumps(data).encode()[:3000], sub["p256dh"], sub["auth"])
    headers = {"TTL": str(ttl), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
               "Urgency": urgency, "Authorization": _vapid_header(sub["endpoint"])}
    if topic:
        headers["Topic"] = topic[:32]
    req = urllib.request.Request(sub["endpoint"], data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):  # subscription gone: forget it
            store.x("DELETE FROM subs WHERE endpoint=?", (sub["endpoint"],))
        return e.code
    except Exception:  # noqa: BLE001
        return 0


def broadcast(title, body, url="/", level="info", tag=None):
    subs = store.q("SELECT * FROM subs")
    payload = {"title": title, "body": body, "url": url, "tag": tag or title[:40], "level": level}
    results = [send(s, payload, urgency="high" if level == "critical" else "normal", topic=None) for s in subs]
    return results
