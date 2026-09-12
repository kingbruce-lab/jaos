from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import math
import time
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AuditLog, SessionToken, User


PBKDF2_ITERATIONS = 600_000
ORGANIZATION_ROLES = {
    "education",
    "administrative",
    "personnel",
    "business",
    "finance",
    "management",
}
LEGACY_ORGANIZATION_ROLE_MAP = {
    "founder": "management",
    "knowledge_admin": "administrative",
    "department_owner": "business",
    "employee": "business",
    "planner": "business",
}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt_hex),
            int(rounds),
        )
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


class LoginRateLimiter:
    def __init__(
        self,
        max_attempts: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._attempts: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = Lock()

    def retry_after(self, key: str, now: float | None = None) -> int:
        current = time.monotonic() if now is None else now
        with self._lock:
            locked_until = self._locked_until.get(key, 0.0)
            if locked_until <= current:
                self._locked_until.pop(key, None)
                return 0
            return max(1, math.ceil(locked_until - current))

    def record_failure(self, key: str, now: float | None = None) -> int:
        current = time.monotonic() if now is None else now
        with self._lock:
            recent = [
                value
                for value in self._attempts.get(key, [])
                if value >= current - self.window_seconds
            ]
            recent.append(current)
            if len(recent) >= self.max_attempts:
                self._attempts.pop(key, None)
                self._locked_until[key] = current + self.lockout_seconds
                return self.lockout_seconds
            self._attempts[key] = recent
            return 0

    def record_success(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()
            self._locked_until.clear()


login_rate_limiter = LoginRateLimiter(
    settings.login_max_attempts,
    settings.login_window_seconds,
    settings.login_lockout_seconds,
)
DUMMY_PASSWORD_HASH = hash_password("jingao-dummy-password-not-an-account")


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def bootstrap_admin(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)):
        migrated_roles = []
        for account in db.scalars(select(User)).all():
            inferred_role = LEGACY_ORGANIZATION_ROLE_MAP.get(
                account.role,
                "business",
            )
            if (
                account.organization_role not in ORGANIZATION_ROLES
                or (
                    account.organization_role == "business"
                    and inferred_role != "business"
                )
            ):
                previous = account.organization_role
                account.organization_role = inferred_role
                migrated_roles.append(
                    {
                        "user_id": account.id,
                        "from": previous,
                        "to": account.organization_role,
                    }
                )
        founders = db.scalars(
            select(User).where(User.role == "founder")
        ).all()
        upgraded = [
            founder
            for founder in founders
            if founder.confidentiality_ceiling != "L5"
        ]
        for founder in upgraded:
            previous = founder.confidentiality_ceiling
            founder.confidentiality_ceiling = "L5"
            db.add(
                AuditLog(
                    user_id=founder.id,
                    action="founder_l5_policy_migration",
                    details_json=json.dumps(
                        {
                            "from": previous,
                            "to": "L5",
                            "reason": "contract_archive_policy_v1",
                        },
                        ensure_ascii=False,
                    ),
                )
            )
        if migrated_roles:
            db.add(
                AuditLog(
                    user_id=None,
                    action="organization_role_migration_v1",
                    details_json=json.dumps(
                        {"accounts": migrated_roles},
                        ensure_ascii=False,
                    ),
                )
            )
        if upgraded or migrated_roles:
            db.commit()
        return
    if not settings.bootstrap_password:
        raise RuntimeError(
            "生产环境首次启动必须设置 JINGAO_BOOTSTRAP_PASSWORD，"
            "且首次登录后应立即更换。"
        )
    db.add(
        User(
            username=settings.bootstrap_username,
            display_name="创始人",
            password_hash=hash_password(settings.bootstrap_password),
            role="founder",
            organization_role="management",
            confidentiality_ceiling="L5",
            departments_json=json.dumps(["*"], ensure_ascii=False),
        )
    )
    db.commit()


def authenticate(db: Session, username: str, password: str) -> User | None:
    normalized = username.strip().lower()
    user = db.scalar(
        select(User).where(
            User.username == normalized,
            User.active.is_(True),
        )
    )
    encoded = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_valid = verify_password(password, encoded)
    if user and password_valid:
        return user
    return None


def create_session(db: Session, user: User) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    db.execute(delete(SessionToken).where(SessionToken.expires_at <= now))
    raw_token = secrets.token_urlsafe(40)
    expires_at = now + timedelta(hours=settings.session_hours)
    db.add(
        SessionToken(
            token_hash=token_digest(raw_token),
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    db.commit()
    return raw_token, expires_at


def revoke_session(db: Session, token: str) -> None:
    db.execute(delete(SessionToken).where(SessionToken.token_hash == token_digest(token)))
    db.commit()


def revoke_user_sessions(db: Session, user_id: str) -> None:
    db.execute(delete(SessionToken).where(SessionToken.user_id == user_id))
    db.commit()


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return authorization.removeprefix("Bearer ").strip()


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _bearer_token(authorization)
    session = db.scalar(
        select(SessionToken).where(SessionToken.token_hash == token_digest(token))
    )
    now = datetime.now(timezone.utc)
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    return user


def raw_bearer_token(authorization: str | None = Header(default=None)) -> str:
    return _bearer_token(authorization)
