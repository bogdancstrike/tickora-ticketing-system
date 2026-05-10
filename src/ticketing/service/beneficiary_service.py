"""Beneficiary lookup/creation. Internal beneficiaries are derived from a Principal."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.common.errors import ValidationError
from src.iam.models import User
from src.iam.principal import Principal
from src.ticketing.models import Beneficiary


def get_or_create_internal(db: Session, principal: Principal) -> Beneficiary:
    """Find or create the Beneficiary row for an internal Principal."""
    row = db.scalar(
        select(Beneficiary).where(
            Beneficiary.user_id == principal.user_id,
            Beneficiary.beneficiary_type == "internal",
        )
    )
    if row is not None:
        return row

    user = db.get(User, principal.user_id)
    row = Beneficiary(
        beneficiary_type="internal",
        user_id     = principal.user_id,
        first_name  = (user.first_name if user else principal.first_name),
        last_name   = (user.last_name  if user else principal.last_name),
        email       = (user.email      if user else principal.email),
    )
    db.add(row)
    db.flush()
    return row


def create_external(db: Session, payload: dict[str, Any]) -> Beneficiary:
    """Create an external beneficiary from a creation payload."""
    if not payload.get("requester_first_name") or not payload.get("requester_last_name"):
        raise ValidationError("external beneficiary requires first and last name")
    row = Beneficiary(
        beneficiary_type="external",
        first_name        = payload.get("requester_first_name"),
        last_name         = payload.get("requester_last_name"),
        email             = payload.get("requester_email"),
        phone             = payload.get("requester_phone"),
        organization_name = payload.get("organization_name"),
        external_identifier = payload.get("external_identifier"),
    )
    db.add(row)
    db.flush()
    return row
