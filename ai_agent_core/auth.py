"""轻量鉴权：PBKDF2 存密码 + 自签 HS256 Token（零第三方依赖）。

为什么不用 PyJWT / passlib：本项目要"拿下来就能跑"，少一个依赖少一个坑。
HS256 的签名逻辑就十几行，实现清楚比引库更可控。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

ALG = "HS256"
DEFAULT_TTL = 8 * 3600
_ITERATIONS = 120_000


# ---------------- base64url ----------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


# ---------------- 密码 ----------------
def hash_password(password: str, salt: str | None = None) -> str:
    """格式：pbkdf2_sha256$迭代次数$盐$哈希"""
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 salt.encode("utf-8"), _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$")
    except (ValueError, AttributeError):
        return False
    if algo != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 salt.encode("utf-8"), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


# ---------------- Token ----------------
@dataclass
class User:
    username: str
    role: str = "advisor"          # admin / advisor
    display_name: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def to_dict(self) -> dict:
        return {"username": self.username, "role": self.role, "name": self.display_name}


def create_token(user: User, secret: str, ttl: int = DEFAULT_TTL) -> str:
    header = {"alg": ALG, "typ": "JWT"}
    payload = {
        "sub": user.username,
        "role": user.role,
        "name": user.display_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
    }
    segments = [
        _b64e(json.dumps(header, separators=(",", ":")).encode()),
        _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()),
    ]
    signing_input = ".".join(segments).encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    segments.append(_b64e(signature))
    return ".".join(segments)


def decode_token(token: str, secret: str) -> User | None:
    """校验签名与过期时间；任何异常都返回 None（调用方统一按 401 处理）。"""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        return None

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_b64d(signature_b64), expected):
            return None
        payload = json.loads(_b64d(payload_b64))
    except Exception:  # noqa: BLE001
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return User(username=payload.get("sub", ""), role=payload.get("role", "advisor"),
                display_name=payload.get("name", ""))


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None
