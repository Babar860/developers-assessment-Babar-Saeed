from datetime import date
from sqlmodel import Session, select

from app.models import (
    User,
    WorkLog,
    Remittance,
    RemittanceItem,
    RemittanceStatus,
)
from app.core import payable_amount


def generate_remittances_for_all_users(*, session: Session) -> int:

    users = session.exec(select(User)).all()
    generated_count = 0

    for user in users:
        worklogs = session.exec(
            select(WorkLog).where(WorkLog.user_id == user.id)
        ).all()

        remittance_items: list[tuple] = []
        total_payable = 0

        for worklog in worklogs:
            amount = payable_amount(session, worklog.id)
            if amount > 0:
                remittance_items.append((worklog.id, amount))
                total_payable += amount

        # Nothing to pay → skip user
        if total_payable <= 0:
            continue

        remittance = Remittance(
            user_id=user.id,
            period_start=date.today().replace(day=1),
            period_end=date.today(),
            status=RemittanceStatus.SUCCESS,
        )

        # Use nested transaction to ensure atomic operation:
        # If item insertion fails, the entire remittance creation rolls back
        with session.begin_nested():
            session.add(remittance)
            session.flush()  # Generate remittance.id without committing
            
            for worklog_id, amount in remittance_items:
                session.add(
                    RemittanceItem(
                        remittance_id=remittance.id,
                        worklog_id=worklog_id,
                        amount=amount,
                    )
                )
        
        session.commit()
        generated_count += 1

    return generated_count
