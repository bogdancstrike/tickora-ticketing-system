"""SLA policy evaluation and maintenance."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session
from framework.commons.logger import logger

from src.ticketing.models import Ticket, SlaPolicy

def evaluate_sla(db: Session, ticket: Ticket) -> None:
    """Evaluate SLA for a ticket and update its due date."""
    if ticket.status in ("done", "closed", "cancelled"):
        return

    policy = _find_matching_policy(db, ticket)
    if not policy:
        logger.debug("no sla policy matches ticket", ticket_id=ticket.id)
        return

    # Calculate SLA due date based on resolution_minutes
    # Note: In a more complex system, we would account for business hours
    if ticket.created_at:
        due_at = ticket.created_at + timedelta(minutes=policy.resolution_minutes)
        
        ticket.sla_due_at = due_at
        
        # Update sla_status based on current time
        now = datetime.now(timezone.utc)
        if now > due_at:
            ticket.sla_status = "breached"
        elif now > (due_at - timedelta(minutes=30)):
            ticket.sla_status = "approaching_breach"
        else:
            ticket.sla_status = "within_sla"
            
        logger.info("sla evaluated", ticket_id=ticket.id, policy_id=policy.id, sla_due_at=due_at.isoformat())

def _find_matching_policy(db: Session, ticket: Ticket) -> Optional[SlaPolicy]:
    """Find the most specific active SLA policy for the ticket."""
    stmt = (
        select(SlaPolicy)
        .where(
            SlaPolicy.is_active.is_(True),
            SlaPolicy.priority == ticket.priority
        )
        .order_by(
            # Sort by specificity: category and beneficiary_type match first
            SlaPolicy.category.desc(),
            SlaPolicy.beneficiary_type.desc()
        )
    )
    
    policies = db.scalars(stmt).all()
    
    for p in policies:
        # Match category if defined in policy
        if p.category and p.category != ticket.category:
            continue
        # Match beneficiary_type if defined in policy
        if p.beneficiary_type and p.beneficiary_type != ticket.beneficiary_type:
            continue
            
        return p
        
    return None

def check_all_breaches(db: Session) -> int:
    """Check for new SLA breaches across all active tickets."""
    now = datetime.now(timezone.utc)
    
    # Update status to 'approaching_breach'
    approaching_stmt = (
        select(Ticket)
        .where(
            Ticket.is_deleted.is_(False),
            Ticket.status.notin_(("done", "closed", "cancelled")),
            Ticket.sla_due_at.is_not(None),
            Ticket.sla_due_at > now,
            Ticket.sla_due_at <= now + timedelta(minutes=30),
            Ticket.sla_status == "within_sla"
        )
    )
    approaching = db.scalars(approaching_stmt).all()
    for t in approaching:
        t.sla_status = "approaching_breach"
        # We could trigger notifications here
        from src.tasking.producer import publish
        publish("notify_sla_approaching", {"ticket_id": t.id})

    # Update status to 'breached'
    breached_stmt = (
        select(Ticket)
        .where(
            Ticket.is_deleted.is_(False),
            Ticket.status.notin_(("done", "closed", "cancelled")),
            Ticket.sla_due_at.is_not(None),
            Ticket.sla_due_at <= now,
            Ticket.sla_status != "breached"
        )
    )
    breached = db.scalars(breached_stmt).all()
    for t in breached:
        t.sla_status = "breached"
        from src.tasking.producer import publish
        publish("notify_sla_breached", {"ticket_id": t.id})
        
    db.commit()
    return len(breached)
