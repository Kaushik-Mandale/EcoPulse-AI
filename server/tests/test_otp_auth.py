import time

import hashlib

from datetime import datetime, timedelta, timezone

import pytest

from fastapi.testclient import TestClient



from server.main import app

from server.database.db import SessionLocal

from server.models.user import User

from server.models.mobile_otp import MobileOtpToken

from server.utils.config import config

from server.services.sms_service import get_sms_provider, set_sms_provider_for_testing, MockSMSProvider, DevelopmentSMSProvider, TwoFactorSMSProvider



client = TestClient(app)



@pytest.fixture(autouse=True)

def cleanup_test_otps(monkeypatch):

    """Ensure clean token states and mock SMS provider before and after each test."""

    monkeypatch.setenv("ENV", "test")

    config.ENV = "test"

    set_sms_provider_for_testing(MockSMSProvider())

    db = SessionLocal()

    try:

        db.query(MobileOtpToken).delete()

        db.commit()

    finally:

        db.close()

    yield

    set_sms_provider_for_testing(None)

    db = SessionLocal()

    try:

        db.query(MobileOtpToken).delete()

        db.commit()

    finally:

        db.close()





def test_01_successful_otp_request_login():

    """1. Successful OTP request for existing registered citizen."""

    res = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})

    assert res.status_code == 200

    data = res.json()

    assert data["success"] is True

    assert "9876543210" in data["phone"]

    assert "otp" not in data  # Never expose OTP in response





def test_02_invalid_mobile_number():

    """2. Invalid mobile number returns 400 Bad Request."""

    invalid_phones = ["12345", "98765abcde", "1234567890", "0000000000", ""]

    for ph in invalid_phones:

        res = client.post("/api/auth/otp/send", json={"phone": ph, "purpose": "login"})

        assert res.status_code in (400, 422)





def test_03_existing_mobile_registration_rejection():

    """3. Registering with an already registered mobile number is rejected with 400."""

    res = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "register"})

    assert res.status_code == 400

    assert "already registered" in res.json()["detail"].lower()





def test_04_successful_otp_verification_login():

    """4. Successful OTP verification logs in the citizen and returns JWT access_token."""

    db = SessionLocal()

    phone = "9876543210"

    otp_code = "654321"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()



    # Store token directly with SHA-256 hash

    token = MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="login",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    )

    db.add(token)

    db.commit()

    db.close()



    res = client.post("/api/auth/login/otp", json={"phone": phone, "otp": otp_code, "role": "citizen"})

    assert res.status_code == 200

    data = res.json()

    assert "access_token" in data

    assert data["token_type"] == "bearer"

    assert data["user"]["role"] == "citizen"





def test_05_incorrect_otp_returns_400():

    """5. Incorrect OTP returns 400 with attempts count."""

    db = SessionLocal()

    phone = "9876543210"

    otp_code = "654321"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()



    token = MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="login",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    )

    db.add(token)

    db.commit()

    db.close()



    res = client.post("/api/auth/login/otp", json={"phone": phone, "otp": "000000", "role": "citizen"})

    assert res.status_code == 400

    assert "invalid" in res.json()["detail"].lower() or "attempts remaining" in res.json()["detail"].lower()





def test_06_expired_otp_returns_400():

    """6. Expired OTP returns 400."""

    db = SessionLocal()

    phone = "9876543210"

    otp_code = "654321"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()



    token = MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="login",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1) # already expired

    )

    db.add(token)

    db.commit()

    db.close()



    res = client.post("/api/auth/login/otp", json={"phone": phone, "otp": otp_code, "role": "citizen"})

    assert res.status_code == 400

    assert "expired" in res.json()["detail"].lower()





def test_07_reused_otp_returns_400():

    """7. Consumed (reused) OTP returns 400."""

    db = SessionLocal()

    phone = "9876543210"

    otp_code = "654321"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()



    token = MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="login",

        attempts=1,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),

        consumed_at=datetime.now(timezone.utc) - timedelta(seconds=10) # already consumed

    )

    db.add(token)

    db.commit()

    db.close()



    res = client.post("/api/auth/login/otp", json={"phone": phone, "otp": otp_code, "role": "citizen"})

    assert res.status_code == 400





def test_08_otp_resend_cooldown():

    """8. Resending OTP within 60s cooldown returns 429 Too Many Requests."""

    res1 = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})

    assert res1.status_code == 200



    res2 = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})

    assert res2.status_code == 429

    assert "please wait" in res2.json()["detail"].lower() or "seconds" in res2.json()["detail"].lower()





def test_09_otp_max_attempts_lockout():

    """9. Exceeding max attempts (5) locks the OTP."""

    db = SessionLocal()

    phone = "9876543210"

    otp_code = "654321"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()



    token = MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="login",

        attempts=4,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    )

    db.add(token)

    db.commit()

    db.close()



    # 5th failed attempt

    res = client.post("/api/auth/login/otp", json={"phone": phone, "otp": "111111", "role": "citizen"})

    assert res.status_code == 400

    assert "maximum" in res.json()["detail"].lower() or "exceeded" in res.json()["detail"].lower()





def test_10_successful_citizen_registration_and_login():

    """10. Successful citizen registration with mobile OTP and subsequent login."""

    db = SessionLocal()

    new_phone = "9777888999"

    db.query(User).filter(User.phone == new_phone).delete()

    db.commit()



    otp_code = "554433"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()

    token = MobileOtpToken(

        phone=new_phone,

        otp_hash=otp_hash,

        purpose="register",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    )

    db.add(token)

    db.commit()

    db.close()



    # Register

    res = client.post("/api/auth/register", json={

        "full_name": "Kavita Shinde",

        "phone": new_phone,

        "otp": otp_code,

        "email": "kavita@dhule.test"

    })

    assert res.status_code == 200

    data = res.json()

    assert "access_token" in data

    assert data["user"]["phone"] == new_phone

    assert data["user"]["role"] == "citizen"



    # Cleanup token and test login

    db = SessionLocal()

    login_otp = "112233"

    login_hash = hashlib.sha256(login_otp.encode("utf-8")).hexdigest()

    db.add(MobileOtpToken(

        phone=new_phone,

        otp_hash=login_hash,

        purpose="login",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    ))

    db.commit()

    db.close()



    res_login = client.post("/api/auth/login/otp", json={

        "phone": new_phone,

        "otp": login_otp,

        "role": "citizen"

    })

    assert res_login.status_code == 200

    assert "access_token" in res_login.json()





def test_11_optional_email_registration():

    """11. Registration without email succeeds; email defaults to null or None."""

    db = SessionLocal()

    phone = "9123456780"

    db.query(User).filter(User.phone == phone).delete()

    db.commit()



    otp_code = "778899"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()

    db.add(MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="register",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    ))

    db.commit()

    db.close()



    res = client.post("/api/auth/register", json={

        "full_name": "Ganesh Patil",

        "phone": phone,

        "otp": otp_code

        # email is omitted entirely

    })

    assert res.status_code == 200

    user_data = res.json()["user"]

    assert user_data["phone"] == phone

    assert user_data["email"] is None





def test_12_driver_public_registration_rejection():

    """12. Drivers cannot self-register through public registration."""

    # Attempting to register as driver via signup/register endpoint should be forced to citizen or rejected

    db = SessionLocal()

    phone = "9123456789"

    db.query(User).filter(User.phone == phone).delete()

    db.commit()



    otp_code = "998877"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()

    db.add(MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="register",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    ))

    db.commit()

    db.close()



    # Even if client passes role="driver", public registration forces citizen role

    res = client.post("/api/auth/register", json={

        "full_name": "Driver Attempt",

        "phone": phone,

        "otp": otp_code,

        "role": "driver"

    })

    if res.status_code == 200:

        assert res.json()["user"]["role"] == "citizen"  # RBAC enforced server-side

    else:

        assert res.status_code == 403





def test_13_jwt_validation_against_me_endpoint():

    """13. JWT token obtained via OTP login validates against /api/auth/me and /api/auth/my."""

    db = SessionLocal()

    phone = "9876543210"

    otp_code = "332211"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()

    db.add(MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="login",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    ))

    db.commit()

    db.close()



    login_res = client.post("/api/auth/login/otp", json={"phone": phone, "otp": otp_code, "role": "citizen"})

    assert login_res.status_code == 200

    token = login_res.json()["access_token"]



    headers = {"Authorization": f"Bearer {token}"}

    me_res = client.get("/api/auth/me", headers=headers)

    assert me_res.status_code == 200

    assert me_res.json()["phone"] == phone



    my_res = client.get("/api/auth/my", headers=headers)

    assert my_res.status_code == 200

    assert my_res.json()["phone"] == phone





def test_14_existing_password_login_backward_compatibility():

    """14. Existing accounts can still log in using password via /api/auth/login."""

    res = client.post("/api/auth/login", json={

        "email": "priya@cityswap.io",

        "password": "Password123!",

        "role": "citizen"

    })

    assert res.status_code == 200

    assert "access_token" in res.json()

    assert res.json()["user"]["email"] == "priya@cityswap.io"





def test_15_rate_limiting_enforcement():

    """15. Mobile number rate limiting enforces max OTPs per 15 minutes window."""

    db = SessionLocal()

    phone = "9898989898"

    # Seed 5 existing tokens within the last 15 minutes

    for i in range(5):

        db.add(MobileOtpToken(

            phone=phone,

            otp_hash="somehash",

            purpose="login",

            attempts=0,

            max_attempts=5,

            created_at=datetime.now(timezone.utc) - timedelta(minutes=i + 1),

            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

        ))

    db.commit()

    db.close()



    res = client.post("/api/auth/otp/send", json={"phone": phone, "purpose": "register"})

    assert res.status_code == 429

    assert "too many" in res.json()["detail"].lower() or "limit" in res.json()["detail"].lower()





def test_16_citizen_cannot_access_driver_or_admin_routes():

    """16. Citizen authenticated via OTP is strictly forbidden from Driver/Admin routes."""

    db = SessionLocal()

    phone = "9876543210"

    otp_code = "889900"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()

    db.add(MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="login",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    ))

    db.commit()

    db.close()



    res = client.post("/api/auth/login/otp", json={"phone": phone, "otp": otp_code, "role": "citizen"})

    assert res.status_code == 200

    token = res.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}



    # Driver route check

    res_driver = client.get("/api/driver/tasks", headers=headers)

    assert res_driver.status_code == 403



    # Admin route check

    res_admin = client.get("/api/admin/metrics", headers=headers)

    assert res_admin.status_code in (403, 404)





def test_17_sms_provider_failure_handling(monkeypatch):

    """17. Gracefully handles SMS provider dispatch failure without exposing internals."""

    class FailingSMSProvider:

        def send_otp(self, phone: str, otp: str) -> bool:

            return False



    set_sms_provider_for_testing(FailingSMSProvider())

    try:

        res = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})

        assert res.status_code == 503

        assert "unable to dispatch" in res.json()["detail"].lower() or "sms" in res.json()["detail"].lower()

    finally:

        monkeypatch.setenv("ENV", "test")

        config.ENV = "test"

        set_sms_provider_for_testing(MockSMSProvider())





def test_18_ip_rate_limiting_enforcement():

    """18. IP rate limiting restricts more than 15 OTP requests per IP within 15 minutes."""

    db = SessionLocal()

    test_ip = "testclient"

    try:

        # Seed 15 tokens from the same test IP

        for i in range(15):

            db.add(MobileOtpToken(

                phone=f"91000000{i:02d}",

                otp_hash="somehash",

                purpose="login",

                ip_address=test_ip,

                attempts=0,

                max_attempts=5,

                created_at=datetime.now(timezone.utc) - timedelta(minutes=1),

                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

            ))

        db.commit()



        res = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})

        assert res.status_code == 429

        assert "rate limit" in res.json()["detail"].lower() or "too many" in res.json()["detail"].lower()

    finally:

        db.query(MobileOtpToken).filter(MobileOtpToken.ip_address == test_ip).delete()

        db.commit()

        db.close()





def test_19_single_use_token_for_registration():

    """19. Once verified and consumed during registration, token cannot be reused."""

    db = SessionLocal()

    phone = "9777888999"

    db.query(User).filter(User.phone == phone).delete()

    db.commit()



    otp_code = "445566"

    otp_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()

    db.add(MobileOtpToken(

        phone=phone,

        otp_hash=otp_hash,

        purpose="register",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    ))

    db.commit()

    db.close()



    # First registration consumes token

    res1 = client.post("/api/auth/register", json={

        "full_name": "Citizen User",

        "phone": phone,

        "otp": otp_code

    })

    assert res1.status_code == 200



    # Second registration attempt with same token fails

    res2 = client.post("/api/auth/register", json={

        "full_name": "Citizen User 2",

        "phone": phone,

        "otp": otp_code

    })

    assert res2.status_code in (400, 429)





def test_20_phone_normalization_handles_various_formats():

    """20. Phone normalization handles +91 prefix, spaces, dashes, leading zero."""

    for ph in ["+91 9876543210", "+91-9876543210", "09876543210", " 9876543210 "]:

        # Reset cooldown for Priya's phone

        db = SessionLocal()

        db.query(MobileOtpToken).filter(MobileOtpToken.phone == "9876543210").delete()

        db.commit()

        db.close()



        res = client.post("/api/auth/otp/send", json={"phone": ph, "purpose": "login"})

        assert res.status_code == 200

        assert res.json()["phone"] == "9876543210"





def test_21_hmac_based_otp_hashing_verification():

    """21. Verifies that OTP hashed with server-side HMAC-SHA256 authenticates successfully."""

    from server.services.auth_service import hash_otp

    db = SessionLocal()

    phone = "9876543210"

    otp_code = "432109"

    otp_hmac = hash_otp(otp_code)



    token = MobileOtpToken(

        phone=phone,

        otp_hash=otp_hmac,

        purpose="login",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    )

    db.add(token)

    db.commit()

    db.close()



    res = client.post("/api/auth/login/otp", json={"phone": phone, "otp": otp_code, "role": "citizen"})

    assert res.status_code == 200

    assert "access_token" in res.json()

    assert res.json()["user"]["phone"] == phone





def test_22_development_sms_provider_refuses_production(monkeypatch):

    """22. DevelopmentSMSProvider refuses to instantiate if ENV is set to production."""

    try:

        monkeypatch.setenv("ENV", "production")

        with pytest.raises(RuntimeError, match="cannot be initialized in production mode"):

            DevelopmentSMSProvider()

    finally:

        monkeypatch.undo()





def test_23_production_mode_disallows_mock_provider_and_returns_503(monkeypatch):

    """23. In production mode, mock/development provider is forbidden and returns 503."""

    from server.services.sms_service import get_sms_provider

    set_sms_provider_for_testing(None)

    try:

        monkeypatch.setenv("ENV", "production")

        monkeypatch.setattr(config, "ENV", "production")

        monkeypatch.setattr(config, "SMS_PROVIDER", "mock")



        with pytest.raises(Exception) as exc_info:

            get_sms_provider()

        assert "503" in str(exc_info.value) or "not configured for production" in str(exc_info.value).lower()

    finally:

        monkeypatch.undo()

        monkeypatch.setenv("ENV", "test")

        config.ENV = "test"

        set_sms_provider_for_testing(MockSMSProvider())





def test_24_production_mode_missing_credentials_returns_503(monkeypatch):

    """24. In production mode, missing SMS credentials for msg91 and 2factor return 503."""

    from server.services.sms_service import get_sms_provider

    set_sms_provider_for_testing(None)

    try:

        monkeypatch.setenv("ENV", "production")

        monkeypatch.setattr(config, "ENV", "production")



        # MSG91 missing API key

        monkeypatch.setattr(config, "SMS_PROVIDER", "msg91")

        monkeypatch.setattr(config, "SMS_API_KEY", "")

        with pytest.raises(Exception) as exc_info:

            get_sms_provider()

        assert "503" in str(exc_info.value)



        # 2Factor missing API key

        monkeypatch.setattr(config, "SMS_PROVIDER", "2factor")

        monkeypatch.setattr(config, "SMS_API_KEY", "")

        with pytest.raises(Exception) as exc_info:

            get_sms_provider()

        assert "503" in str(exc_info.value)

    finally:

        monkeypatch.undo()

        monkeypatch.setenv("ENV", "test")

        config.ENV = "test"

        set_sms_provider_for_testing(MockSMSProvider())





def test_25_twofactor_provider_interface():

    """25. TwoFactorSMSProvider implements the SMSProvider interface and handles missing keys safely."""

    from server.services.sms_service import TwoFactorSMSProvider

    provider_missing = TwoFactorSMSProvider(api_key="")

    assert provider_missing.provider_name == "2factor"

    assert provider_missing.send_otp("9876543210", "123456") is False





def test_26_atomic_verification_prevents_concurrent_reuse():

    """26. Atomic verification ensures an OTP cannot be consumed more than once."""

    from server.services.auth_service import hash_otp, AuthService

    db = SessionLocal()

    phone = "9876543210"

    otp_code = "789123"

    token = MobileOtpToken(

        phone=phone,

        otp_hash=hash_otp(otp_code),

        purpose="login",

        attempts=0,

        max_attempts=5,

        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)

    )

    db.add(token)

    db.commit()

    db.close()



    # First verification succeeds

    res1 = client.post("/api/auth/login/otp", json={"phone": phone, "otp": otp_code, "role": "citizen"})

    assert res1.status_code == 200



    # Second immediate verification fails because token was atomically marked consumed

    res2 = client.post("/api/auth/login/otp", json={"phone": phone, "otp": otp_code, "role": "citizen"})

    assert res2.status_code == 400

    assert "active verification code" in res2.json()["detail"].lower() or "consumed" in res2.json()["detail"].lower()
