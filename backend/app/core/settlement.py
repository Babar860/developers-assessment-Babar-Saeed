from decimal import Decimal
from sqlmodel import Session, select
from app.models import (
    TimeSegment,
    Adjustment,
    RemittanceItem,
    Remittance,
    RemittanceStatus,
)

RATE_PER_MINUTE = Decimal("0.50")


def total_earned(session: Session, worklog_id):
    minutes = session.exec(
        select(TimeSegment.minutes).where(TimeSegment.worklog_id == worklog_id)
    ).all()
    total_minutes = sum(minutes) if minutes else 0

    adjustments = session.exec(
        select(Adjustment.amount).where(Adjustment.worklog_id == worklog_id)
    ).all()
    adjustment_total = sum(adjustments) if adjustments else Decimal("0")

    return (Decimal(total_minutes) * RATE_PER_MINUTE) + adjustment_total


def total_remitted(session: Session, worklog_id):
    remitted = session.exec(
        select(RemittanceItem.amount)
        .join(Remittance, Remittance.id == RemittanceItem.remittance_id)
        .where(
            RemittanceItem.worklog_id == worklog_id,
            Remittance.status == RemittanceStatus.SUCCESS,
        )
    ).all()

    return sum(remitted) if remitted else Decimal("0")


def payable_amount(session: Session, worklog_id):
    return total_earned(session, worklog_id) - total_remitted(session, worklog_id)
