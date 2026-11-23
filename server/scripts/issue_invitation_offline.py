"""Issue a staff invitation offline and write its activation link once.

This command never falls back to ``DATABASE_URL`` and only accepts explicitly
designated local/disposable targets. It deliberately has no production bypass.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import re
import secrets
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from server.database.target_guard import (
    DISPOSABLE_AUTHORIZATION,
    DISPOSABLE_DATABASE_RE,
    PRODUCTION_DATABASE_RE,
    TargetSafetyError,
    describe_target,
    redact_text,
    validate_connection,
    validate_target_url,
)

ALLOWED_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Secure offline staff invitation provisioning.")
    parser.add_argument("--url", required=True, help="Explicit local/disposable SQLAlchemy database URL; never defaults to DATABASE_URL.")
    parser.add_argument("--environment", required=True, choices=sorted(ALLOWED_ENVIRONMENTS), help="Explicit non-production environment.")
    parser.add_argument("--authorize-disposable-target", required=True, choices=[DISPOSABLE_AUTHORIZATION], help="Explicitly designate the target disposable.")
    parser.add_argument("--actor-employee-id", required=True, help="Issuing administrator's employee ID.")
    parser.add_argument("--role", required=True, choices=["admin", "driver", "collector"], help="Invitee role.")
    parser.add_argument("--full-name", help="Invitee name for a new account.")
    parser.add_argument("--employee-id", help="Invitee municipal employee ID for a new account.")
    parser.add_argument("--email", help="Optional invitee email.")
    parser.add_argument("--phone", help="Required for Drivers; optional otherwise.")
    parser.add_argument("--ward", help="Required for Drivers and Collectors.")
    parser.add_argument("--vehicle-assignment", help="Optional Driver vehicle assignment.")
    parser.add_argument("--reset-user-id", type=int, help="Reset an existing eligible invited account instead of creating a new one.")
    parser.add_argument("--frontend-origin", required=True, help="Frontend origin used to construct the activation URL.")
    parser.add_argument("--output-file", required=True, type=Path, help="New protected file outside this repository for one-time delivery.")
    return parser


def _validate_origin(origin: str) -> str:
    value = origin.strip().rstrip("/")
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::\d{1,5})?|http://(?:localhost|127\.0\.0\.1)(?::\d{1,5})?", value):
        raise ValueError("Frontend origin must be an HTTPS origin (or loopback HTTP for local testing).")
    return value


def _secure_output(path: Path, contents: str) -> None:
    """Create a new protected file; fail closed if the OS ACL/mode cannot be set."""
    path = path.expanduser().absolute()
    parent = path.parent.resolve(strict=True)
    path = parent / path.name
    try:
        path.relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise ValueError("Sensitive invitation output must be outside the repository.")
    encoded = contents.encode("utf-8")
    if os.name == "nt":
        _secure_windows_create(path, encoded)
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            raise OSError("Could not establish owner-only permissions on invitation output.")
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            path.unlink()
        except OSError:
            pass
        raise
    else:
        os.close(fd)


def _secure_windows_create(path: Path, contents: bytes) -> None:
    """Create with a protected DACL granting access only to the current user."""
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise OSError(ctypes.get_last_error(), "Could not inspect current Windows user permissions.")
    try:
        needed = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token, 1, buffer, needed, ctypes.byref(needed)):
            raise OSError(ctypes.get_last_error(), "Could not inspect current Windows user permissions.")
        sid_pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        sid_text = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid_pointer, ctypes.byref(sid_text)):
            raise OSError(ctypes.get_last_error(), "Could not establish invitation output permissions.")
        try:
            sddl = f"D:P(A;;FA;;;{sid_text.value})"
            descriptor = ctypes.c_void_p()
            if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
                raise OSError(ctypes.get_last_error(), "Could not establish invitation output permissions.")
            try:
                class SECURITY_ATTRIBUTES(ctypes.Structure):
                    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p), ("bInheritHandle", wintypes.BOOL)]
                attributes = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), descriptor, False)
                kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
                kernel.CreateFileW.restype = wintypes.HANDLE
                kernel.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
                kernel.WriteFile.restype = wintypes.BOOL
                kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
                kernel.FlushFileBuffers.restype = wintypes.BOOL
                handle = kernel.CreateFileW(str(path), 0x40000000, 0, ctypes.byref(attributes), 1, 0x80, None)
                invalid_handle = ctypes.c_void_p(-1).value
                if handle == invalid_handle:
                    raise OSError(ctypes.get_last_error(), "Could not create protected invitation output file.")
                try:
                    written = wintypes.DWORD()
                    data_buffer = ctypes.create_string_buffer(contents)
                    if not kernel.WriteFile(handle, data_buffer, len(contents), ctypes.byref(written), None) or written.value != len(contents):
                        raise OSError(ctypes.get_last_error(), "Could not write protected invitation output file.")
                    if not kernel.FlushFileBuffers(handle):
                        raise OSError(ctypes.get_last_error(), "Could not flush protected invitation output file.")
                except Exception:
                    kernel.CloseHandle(handle)
                    try:
                        path.unlink()
                    except OSError:
                        pass
                    raise
                kernel.CloseHandle(handle)
            finally:
                kernel.LocalFree(descriptor)
        finally:
            kernel.LocalFree(sid_text)
    finally:
        kernel.CloseHandle(token)


def _validate_operator(db: Session, employee_id: str, password: str, code: str) -> tuple[User, int]:
    from server.models.user import User
    from server.services.iam_service import authenticate_password, decrypt_mfa_secret, verify_totp

    actor = db.query(User).filter(User.employee_id == employee_id.strip()).one_or_none()
    if (
        not actor or actor.role != "admin" or not actor.is_active or not actor.is_verified
        or actor.account_status != "active" or not actor.mfa_enabled or not actor.mfa_secret_enc
        or not authenticate_password(actor, password)
    ):
        raise ValueError("Issuing administrator identity could not be verified.")
    step = verify_totp(decrypt_mfa_secret(actor.mfa_secret_enc), code)
    if step is None or (actor.mfa_last_verified_step is not None and step <= actor.mfa_last_verified_step):
        raise ValueError("A current, unused authenticator code is required.")
    return actor, step


def _validate_role(actor: User, role: str, employee_id: str | None) -> None:
    if actor.is_super_admin:
        if role != "admin":
            raise ValueError("Super Admin may use this offline workflow only to provision Municipal Admins.")
    elif role not in {"driver", "collector"}:
        raise ValueError("Only Super Admin may provision Municipal Admins.")
    if role == "admin":
        if not employee_id:
            raise ValueError("Municipal Admin invitation requires an employee ID.")


def _make_new_user(db: Session, args, actor: User) -> User:
    from server.models.user import User
    from server.services.auth_service import normalize_phone_number

    name = (args.full_name or "").strip()
    employee_id = (args.employee_id or "").strip()
    ward = (args.ward or "").strip()
    if len(name) < 2 or not employee_id:
        raise ValueError("New invitation requires --full-name and --employee-id.")
    if args.role in {"driver", "collector"} and not ward:
        raise ValueError(f"{args.role.title()} invitation requires --ward.")
    phone = normalize_phone_number(args.phone) if args.phone else None
    if args.role == "driver" and (not phone or len(phone) != 10):
        raise ValueError("Driver invitation requires a valid 10-digit --phone.")
    email = args.email.strip().lower() if args.email else None
    duplicate = db.query(User).filter(
        (User.employee_id == employee_id)
        | ((User.email == email) if email else False)
        | ((User.phone == phone) if phone else False)
    ).first()
    if duplicate:
        raise ValueError("Employee ID, email, or phone is already assigned.")
    user = User(
        full_name=name, employee_id=employee_id, email=email, phone=phone,
        role=args.role, ward=ward or None,
        vehicle_assignment=args.vehicle_assignment if args.role == "driver" else None,
        hashed_password=None, is_active=False, is_verified=False,
        account_status="pending", created_by_id=actor.id,
        approved_by_id=actor.id if args.role == "admin" else None,
    )
    db.add(user)
    db.flush()
    return user


def _prepare_reset(db: Session, args, actor: User) -> User:
    from server.models.account_invitation import AccountInvitation
    from server.models.user import User
    from server.services.iam_service import audit

    target = db.query(User).filter(User.id == args.reset_user_id, User.role == args.role).one_or_none()
    if not target or target.is_super_admin or target.id == actor.id:
        raise ValueError("Target account was not found or is not eligible for invitation reset.")
    if target.account_status in {"retired", "deactivated", "suspended"}:
        raise ValueError("Suspended or retired accounts cannot receive a replacement invitation.")
    if args.role == "admin" and not actor.is_super_admin:
        raise ValueError("Only Super Admin may reset a Municipal Admin invitation.")
    now = datetime.now(timezone.utc)
    invalidated = db.query(AccountInvitation).filter(
        AccountInvitation.user_id == target.id,
        AccountInvitation.consumed_at.is_(None),
        AccountInvitation.revoked_at.is_(None),
    ).update({"revoked_at": now}, synchronize_session=False)
    if invalidated:
        audit(db, f"{args.role}_invitation_invalidated", actor=actor, target=target)
    target.is_active = False
    target.account_status = "pending"
    target.hashed_password = None
    target.session_version = (target.session_version or 0) + 1
    if args.role in {"admin", "collector"}:
        target.mfa_enabled = False
        target.mfa_secret_enc = None
        target.mfa_last_verified_step = None
    audit(db, f"{args.role}_invitation_reset", actor=actor, target=target)
    return target


def main(argv=None, *, input_fn=input, password_fn=getpass.getpass) -> int:
    args = build_parser().parse_args(argv)
    if args.environment not in ALLOWED_ENVIRONMENTS:
        print("Refusing unsupported environment.", file=sys.stderr)
        return 2
    try:
        url = validate_target_url(
            args.url,
            disposable_authorization=args.authorize_disposable_target,
            require_disposable=True,
        )
        parsed_target = make_url(url)
        if parsed_target.drivername.startswith("sqlite"):
            target_name = Path(parsed_target.database or "").stem
            if not DISPOSABLE_DATABASE_RE.search(target_name) or PRODUCTION_DATABASE_RE.search(target_name):
                raise ValueError("SQLite target filename must clearly identify test, dev, local, disposable, or CI use.")
        origin = _validate_origin(args.frontend_origin)
        output = args.output_file.expanduser().absolute()
        if args.reset_user_id is None and (not args.full_name or not args.employee_id):
            raise ValueError("New invitation requires --full-name and --employee-id.")
        if args.reset_user_id is not None and any((args.full_name, args.employee_id, args.email, args.phone, args.ward, args.vehicle_assignment)):
            raise ValueError("Do not provide new-account fields when resetting an invitation.")
        if input_fn("Type RESET to invalidate the existing invitation and issue a replacement, or ISSUE to issue a new invitation: ").strip() != ("RESET" if args.reset_user_id else "ISSUE"):
            print("No invitation was created.", file=sys.stderr)
            return 2
    except (TargetSafetyError, ValueError) as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2

    # ORM imports construct the application's default engine at import time.
    # Pin both variables to the already validated explicit target before importing
    # any model/service module; DATABASE_URL is never consulted as a fallback.
    previous_database_url = os.environ.get("DATABASE_URL")
    previous_environment = os.environ.get("ENV")
    load_dotenv(override=False)
    os.environ["DATABASE_URL"] = url
    os.environ["ENV"] = args.environment
    engine = create_engine(url, pool_pre_ping=True)
    db = None
    output_written = False
    try:
        validate_connection(engine)
        import server.models  # noqa: F401 - register all ORM tables for the explicit target.
        from server.models.account_invitation import AccountInvitation
        from server.models.user import User
        from server.services.iam_service import audit, issue_invitation
        db = sessionmaker(bind=engine, expire_on_commit=False)()
        actor, step = _validate_operator(
            db,
            args.actor_employee_id,
            password_fn("Administrator password: "),
            password_fn("Current authenticator code: "),
        )
        if args.reset_user_id is None:
            _validate_role(actor, args.role, args.employee_id)
        elif args.role != "admin":
            _validate_role(actor, args.role, None)
        if args.reset_user_id is not None:
            reset_candidate = db.query(User).filter(
                User.id == args.reset_user_id, User.role == args.role,
            ).one_or_none()
            if not reset_candidate:
                raise ValueError("Target account was not found or is not eligible for invitation reset.")
            _validate_role(actor, args.role, reset_candidate.employee_id if args.role == "admin" else None)
            user = _prepare_reset(db, args, actor)
        else:
            user = _make_new_user(db, args, actor)
            if args.role == "collector":
                audit(db, "collector_provisioned", actor=actor, target=user)
            elif args.role == "admin":
                audit(db, "admin_provisioned", actor=actor, target=user)

        token = issue_invitation(
            db, user, args.role, actor,
            approved_by=actor if args.role == "admin" else None,
        )
        actor.mfa_last_verified_step = step
        activation_url = f"{origin}/activate#token={quote(token, safe='')}"
        _secure_output(output, activation_url + "\n")
        output_written = True
        db.commit()
        print(f"Invitation issued for {user.employee_id} ({args.role}); expires in 24 hours.")
        print(f"One-time activation link written to: {output}")
        print("Deliver privately; avoid screenshots/shared logs. Delete the temporary file after delivery. Never commit it. Secure deletion of storage media is not guaranteed.")
        return 0
    except Exception as exc:
        if db is not None:
            db.rollback()
        if output_written:
            try:
                output.unlink()
            except OSError:
                print("Warning: could not remove the uncommitted sensitive output file.", file=sys.stderr)
        safe_detail = redact_text(exc)
        print(f"Invitation was not completed ({type(exc).__name__}: {safe_detail}). No token is included in this diagnostic.", file=sys.stderr)
        return 1
    finally:
        if db is not None:
            db.close()
        engine.dispose()
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        if previous_environment is None:
            os.environ.pop("ENV", None)
        else:
            os.environ["ENV"] = previous_environment


if __name__ == "__main__":
    raise SystemExit(main())
