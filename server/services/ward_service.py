"""Canonical municipality and ward lookup helpers shared by admin APIs."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from server.models.municipality import Municipality
from server.models.user import User
from server.models.ward import Ward


def actor_municipality_ids(db: Session, actor: User) -> set[int] | None:
    if actor.is_super_admin:
        return None
    if actor.ward_id:
        ward = db.query(Ward).filter(Ward.id == actor.ward_id).first()
        if ward:
            municipality = db.query(Municipality).filter(Municipality.id == ward.municipality_id,
                                                         Municipality.is_active.is_(True)).first()
            if municipality:
                return {municipality.id}
            raise HTTPException(status_code=403, detail="This account's municipality is inactive.")
    if actor.municipality_id:
        if db.query(Municipality.id).filter(Municipality.id == actor.municipality_id,
                                            Municipality.is_active.is_(True)).first():
            return {actor.municipality_id}
        raise HTTPException(status_code=403, detail="This account's municipality is inactive.")
    # Existing single-municipality installations have no explicit association
    # on legacy Municipal Admin records. Preserve their scope only while that
    # scope is unambiguous; a second municipality requires explicit assignment.
    active_ids = {row.id for row in db.query(Municipality.id).filter(Municipality.is_active.is_(True)).all()}
    if len(active_ids) == 1:
        return active_ids
    raise HTTPException(status_code=403, detail="This account has no unambiguous municipality assignment.")


def resolve_active_ward(db: Session, actor: User, ward_id: int) -> Ward:
    ward = db.query(Ward).filter(Ward.id == ward_id).first()
    if not ward:
        raise HTTPException(status_code=422, detail="Select an existing ward from the registry.")
    if not ward.is_active:
        raise HTTPException(status_code=422, detail="Staff cannot be assigned to an inactive ward.")
    allowed = actor_municipality_ids(db, actor)
    if allowed is not None and ward.municipality_id not in allowed:
        raise HTTPException(status_code=403, detail="You may assign staff only within your municipality.")
    if not actor.is_super_admin:
        scoped_ward_id = actor.ward_id
        if scoped_ward_id is None and (actor.ward or "").strip():
            legacy_scope = db.query(Ward).filter(
                Ward.municipality_id == ward.municipality_id,
                Ward.display_name.ilike((actor.ward or "").strip()),
            ).first()
            scoped_ward_id = legacy_scope.id if legacy_scope else None
        if scoped_ward_id is not None and scoped_ward_id != ward.id:
            raise HTTPException(status_code=403, detail="You may assign staff only in your assigned ward.")
    municipality = db.query(Municipality).filter(
        Municipality.id == ward.municipality_id, Municipality.is_active.is_(True)
    ).first()
    if not municipality:
        raise HTTPException(status_code=422, detail="The ward municipality is inactive.")
    return ward


def ensure_staff_scope(db: Session, actor: User, target: User) -> None:
    """Fail closed when a Municipal Admin's staff target is outside scope."""
    if actor.is_super_admin:
        return
    allowed = actor_municipality_ids(db, actor)
    target_municipality_id = target.municipality_id
    effective_target_ward_id = target.ward_id

    if target_municipality_id is None and target.ward_id:
        target_ward = db.query(Ward).filter(Ward.id == target.ward_id).first()
        target_municipality_id = target_ward.municipality_id if target_ward else None

    if (target_municipality_id is None or effective_target_ward_id is None) and (target.ward or "").strip() and allowed:
        matched_ward = db.query(Ward).filter(
            Ward.municipality_id.in_(allowed), Ward.display_name.ilike((target.ward or "").strip())
        ).first()
        if matched_ward:
            if effective_target_ward_id is None:
                effective_target_ward_id = matched_ward.id
            if target_municipality_id is None:
                target_municipality_id = matched_ward.municipality_id

    if target_municipality_id is None and allowed and len(allowed) == 1:
        target_municipality_id = next(iter(allowed))

    if allowed is not None and target_municipality_id not in allowed:
        raise HTTPException(status_code=403, detail="You may manage staff only within your municipality.")

    scoped_ward_id = actor.ward_id
    if scoped_ward_id is None and (actor.ward or "").strip() and allowed:
        scoped_ward = db.query(Ward).filter(
            Ward.municipality_id.in_(allowed), Ward.display_name.ilike((actor.ward or "").strip())
        ).first()
        scoped_ward_id = scoped_ward.id if scoped_ward else None

    if scoped_ward_id is not None and effective_target_ward_id != scoped_ward_id:
        raise HTTPException(status_code=403, detail="You may manage staff only in your assigned ward.")

    actor_ward_str = (actor.ward or "").strip()
    target_ward_str = (target.ward or "").strip()
    if actor_ward_str and target_ward_str and actor_ward_str.casefold() != target_ward_str.casefold():
        raise HTTPException(status_code=403, detail="You may manage staff only in your assigned ward.")
