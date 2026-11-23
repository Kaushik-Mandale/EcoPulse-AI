import os
import time

from cryptography.fernet import Fernet
from sqlalchemy.orm import object_session

from server.services.iam_service import _totp_code, encrypt_mfa_secret, make_access_token
from server.utils.security import create_access_token


TEST_FERNET_KEY = Fernet.generate_key().decode("ascii")
TEST_TOTP_SECRET = "JBSWY3DPEHPK3PXP"


def prepare_admin_mfa(user):
    os.environ["MFA_ENCRYPTION_KEY"] = TEST_FERNET_KEY
    user.mfa_enabled = True
    user.mfa_secret_enc = encrypt_mfa_secret(TEST_TOTP_SECRET)
    user.mfa_last_verified_step = None
    user.is_active = True
    user.is_locked = False
    user.account_status = "active"
    user.is_verified = True


def admin_access_token(user):
    user.mfa_enabled = True
    user.is_active = True
    user.is_locked = False
    user.account_status = "active"
    user.is_verified = True
    session = object_session(user)
    if session is not None:
        session.commit()
    return make_access_token(user, f"test-session-{user.id}")


def login_admin(client, user, password):
    prepare_admin_mfa(user)
    session = object_session(user)
    if session is not None:
        session.commit()
    code = _totp_code(TEST_TOTP_SECRET, int(time.time() // 30))
    return client.post(
        "/api/auth/login",
        json={
            "email": user.employee_id,
            "password": password,
            "role": user.role,
            "mfa_code": code,
        },
    )


def citizen_access_token(user):
    return create_access_token({
        "sub": user.email or user.phone,
        "role": user.role,
        "id": user.id,
        "sv": user.session_version or 0,
    })
