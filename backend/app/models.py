import uuid
from decimal import Decimal
from enum import Enum
from datetime import datetime, date

from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)
    worklogs: list["WorkLog"] = Relationship(back_populates="user", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str

# WORKLOG SETTLEMENT MODELS
class RemittanceStatus(str, Enum):
    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

class WorkLog(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="user.id", 
        index = True,
        nullable=False, 
        ondelete="CASCADE")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user: User = Relationship(back_populates="worklogs")
    time_segments: list["TimeSegment"] = Relationship(back_populates="worklog", cascade_delete=True)
    adjustment: list["Adjustment"] = Relationship(back_populates="worklog",  cascade_delete=True)

class TimeSegment(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    worklog_id: uuid.UUID = Field(
        foreign_key="worklog.id", 
        index = True,
        nullable=False, 
        ondelete="CASCADE")
    minutes: int = Field(gt=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    worklog: WorkLog = Relationship(back_populates="time_segments")

class Adjustment(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    worklog_id: uuid.UUID = Field(
        foreign_key="worklog.id", 
        index = True,
        nullable=False, 
        ondelete="CASCADE")
    amount: Decimal
    reason: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    worklog: WorkLog = Relationship(back_populates="adjustment")

class Remittance(SQLModel, table=True):
    """
    A payout attempt for a user.
    Only SUCCESS remittances count financially.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        index=True,
        nullable=False,
        ondelete="CASCADE",
    )
    period_start: date
    period_end: date
    status: RemittanceStatus
    created_at: datetime = Field(default_factory=datetime.utcnow)

    items: list["RemittanceItem"] = Relationship(
        back_populates="remittance",
        cascade_delete=True
    )

class RemittanceItem(SQLModel, table=True):
    """
    Immutable snapshot of what was paid for a WorkLog.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    remittance_id: uuid.UUID = Field(
        foreign_key="remittance.id",
        index=True,
        nullable=False,
        ondelete="CASCADE",
    )
    worklog_id: uuid.UUID = Field(
        foreign_key="worklog.id",
        index=True,
        nullable=False,
        ondelete="CASCADE",
    )
    amount: Decimal

    remittance: Remittance = Relationship(back_populates="items")

# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
