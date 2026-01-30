from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.api.deps import get_db
from app.schemas.worklog import WorkLogListResponse, WorkLogPublic
from app.schemas.remittance import GenerateRemittanceResponse
from app.models import WorkLog
from app.core import payable_amount
from app.api.routes.settlements.service import (
    generate_remittances_for_all_users,
)

router = APIRouter()


@router.post(
    "/generate-remittances-for-all-users",
    response_model=GenerateRemittanceResponse,
)
def generate_remittances(
    session: Session = Depends(get_db),
):
    
    generated = generate_remittances_for_all_users(session=session)

    return GenerateRemittanceResponse(
        status="success",
        generated=generated,
    )


@router.get(
    "/list-all-worklogs",
    response_model=WorkLogListResponse,
)
def list_all_worklogs(
    remittanceStatus: str | None = Query(
        default=None,
        regex="^(REMITTED|UNREMITTED)$",
    ),
    session: Session = Depends(get_db),
):

    worklogs = session.exec(select(WorkLog)).all()
    data: list[WorkLogPublic] = []

    for worklog in worklogs:
        amount = payable_amount(session, worklog.id)
        status = "REMITTED" if amount <= 0 else "UNREMITTED"

        if remittanceStatus and remittanceStatus != status:
            continue

        data.append(
            WorkLogPublic(
                worklog_id=worklog.id,
                user_id=worklog.user_id,
                amount=amount,
                remittance_status=status,
            )
        )

    return WorkLogListResponse(
        data=data,
        count=len(data),
    )
