from decimal import Decimal
from uuid import UUID
from sqlmodel import SQLModel


class WorkLogPublic(SQLModel):
    
    worklog_id: UUID
    user_id: UUID
    amount: Decimal
    remittance_status: str  # REMITTED | UNREMITTED


class WorkLogListResponse(SQLModel):

    data: list[WorkLogPublic]
    count: int
