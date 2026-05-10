"""Service for managing custom ticket metadata."""
from typing import Any, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from framework.commons.logger import logger

from src.common.errors import PermissionDeniedError
from src.iam import rbac
from src.iam.principal import Principal
from src.ticketing.models import Ticket, TicketMetadata
from src.audit import service as audit_service
from src.ticketing.service import ticket_service
from src.audit import events

def list_by_ticket(db: Session, principal: Principal, ticket_id: str) -> List[TicketMetadata]:
    """List all metadata for a specific ticket."""
    ticket = ticket_service.get(db, principal, ticket_id)
    # can_view_ticket check is already in ticket_service.get
    
    stmt = select(TicketMetadata).where(TicketMetadata.ticket_id == ticket_id).order_by(TicketMetadata.key.asc())
    return list(db.scalars(stmt))

def set_metadata(
    db: Session, 
    principal: Principal, 
    ticket_id: str, 
    key: str, 
    value: str, 
    label: Optional[str] = None
) -> TicketMetadata:
    """Set (upsert) a metadata key-value pair for a ticket."""
    ticket = ticket_service.get(db, principal, ticket_id)
    if not rbac.can_modify_ticket(principal, ticket):
        raise PermissionDeniedError("not allowed to modify metadata for this ticket")
    
    key = key.strip().lower()
    value = value.strip()
    
    meta = db.scalar(
        select(TicketMetadata).where(
            TicketMetadata.ticket_id == ticket_id,
            TicketMetadata.key == key
        )
    )
    
    old_val = meta.value if meta else None
    
    if meta:
        meta.value = value
        if label:
            meta.label = label
    else:
        meta = TicketMetadata(
            ticket_id=ticket_id,
            key=key,
            value=value,
            label=label
        )
        db.add(meta)
    
    db.flush()
    
    if old_val != value:
        audit_service.record(
            db,
            actor=principal,
            action=events.TICKET_UPDATED,
            entity_type="ticket_metadata",
            entity_id=meta.id,
            ticket_id=ticket_id,
            old_value={"key": key, "value": old_val},
            new_value={"key": key, "value": value},
            metadata={"metadata_key": key}
        )
        
    return meta

def delete_metadata(db: Session, principal: Principal, ticket_id: str, key: str) -> None:
    """Remove a metadata entry."""
    ticket = ticket_service.get(db, principal, ticket_id)
    if not rbac.can_modify_ticket(principal, ticket):
        raise PermissionDeniedError("not allowed to modify metadata for this ticket")
        
    meta = db.scalar(
        select(TicketMetadata).where(
            TicketMetadata.ticket_id == ticket_id,
            TicketMetadata.key == key
        )
    )
    if meta:
        old_val = meta.value
        db.delete(meta)
        db.flush()
        
        audit_service.record(
            db,
            actor=principal,
            action=events.TICKET_UPDATED,
            entity_type="ticket_metadata",
            entity_id=ticket_id,
            ticket_id=ticket_id,
            old_value={"key": key, "value": old_val},
            new_value=None,
            metadata={"metadata_key": key, "op": "delete"}
        )
