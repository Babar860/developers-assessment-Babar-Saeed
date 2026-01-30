"""
Tests for the Settlements API routes.

Tests validate:
- WorkLog model creation and relationships
- Settlement calculation logic (earned, remitted, payable amounts)
- Remittance generation for all users
- WorkLog listing with optional remittance status filtering
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.models import (
    User,
    WorkLog,
    TimeSegment,
    Adjustment,
    Remittance,
    RemittanceItem,
    RemittanceStatus,
)
from app.core.settlement import (
    total_earned,
    total_remitted,
    payable_amount,
    RATE_PER_MINUTE,
)
from app.core.db import engine, init_db
from app.main import app


@pytest.fixture(scope="module")
def settlement_db() -> Session:
    """Create a fresh database session for settlement tests."""
    with Session(engine) as session:
        init_db(session)
        yield session


@pytest.fixture(scope="module")
def settlement_client() -> TestClient:
    """Create a test client for settlement API endpoints."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_settlement_data(settlement_db: Session):
    """Clean up all settlement-related data after each test."""
    yield
    settlement_db.exec(delete(RemittanceItem))
    settlement_db.exec(delete(Remittance))
    settlement_db.exec(delete(Adjustment))
    settlement_db.exec(delete(TimeSegment))
    settlement_db.exec(delete(WorkLog))
    settlement_db.exec(delete(User))
    settlement_db.commit()


class TestWorkLogModel:
    """Test WorkLog model and its relationships."""

    def test_worklog_creation(self, settlement_db: Session):
        """Test creating a WorkLog record."""
        user = User(
            id=uuid4(),
            email="worklog.test@example.com",
            hashed_password="hashed_pwd",
            full_name="Test User",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()
        settlement_db.refresh(worklog)

        assert worklog.id is not None
        assert worklog.user_id == user.id
        assert worklog.created_at is not None
        assert worklog.time_segments == []
        assert worklog.adjustment == []

    def test_worklog_cascade_delete_on_user_delete(self, settlement_db: Session):
        """Test that WorkLogs are deleted when User is deleted."""
        user = User(
            id=uuid4(),
            email="cascade.test@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        worklog_id = worklog.id
        settlement_db.delete(user)
        settlement_db.commit()

        deleted = settlement_db.get(WorkLog, worklog_id)
        assert deleted is None


class TestTimeSegmentModel:
    """Test TimeSegment model and validation."""

    def test_time_segment_creation(self, settlement_db: Session):
        """Test creating TimeSegment with valid minutes."""
        user = User(
            id=uuid4(),
            email="timeseg.test@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=120
        )
        settlement_db.add(segment)
        settlement_db.commit()
        settlement_db.refresh(segment)

        assert segment.minutes == 120
        assert segment.created_at is not None

    def test_time_segment_cascade_delete(self, settlement_db: Session):
        """Test that TimeSegments are deleted when WorkLog is deleted."""
        user = User(
            id=uuid4(),
            email="timeseg.cascade@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=60
        )
        settlement_db.add(segment)
        settlement_db.commit()

        segment_id = segment.id
        settlement_db.delete(worklog)
        settlement_db.commit()

        deleted = settlement_db.get(TimeSegment, segment_id)
        assert deleted is None


class TestAdjustmentModel:
    """Test Adjustment model."""

    def test_adjustment_creation(self, settlement_db: Session):
        """Test creating an Adjustment."""
        user = User(
            id=uuid4(),
            email="adjustment.test@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        adjustment = Adjustment(
            id=uuid4(),
            worklog_id=worklog.id,
            amount=Decimal("10.50"),
            reason="Bonus for overtime",
        )
        settlement_db.add(adjustment)
        settlement_db.commit()
        settlement_db.refresh(adjustment)

        assert adjustment.amount == Decimal("10.50")
        assert adjustment.reason == "Bonus for overtime"

    def test_adjustment_cascade_delete(self, settlement_db: Session):
        """Test that Adjustments are deleted when WorkLog is deleted."""
        user = User(
            id=uuid4(),
            email="adjustment.cascade@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        adjustment = Adjustment(
            id=uuid4(),
            worklog_id=worklog.id,
            amount=Decimal("5.00"),
            reason="Penalty",
        )
        settlement_db.add(adjustment)
        settlement_db.commit()

        adjustment_id = adjustment.id
        settlement_db.delete(worklog)
        settlement_db.commit()

        deleted = settlement_db.get(Adjustment, adjustment_id)
        assert deleted is None


class TestSettlementCalculations:
    """Test settlement calculation functions."""

    def test_total_earned_with_time_segments_only(self, settlement_db: Session):
        """Test total_earned with only time segments."""
        user = User(
            id=uuid4(),
            email="calc.time@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        # Add 100 minutes → 100 * 0.50 = 50.00
        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=100
        )
        settlement_db.add(segment)
        settlement_db.commit()

        earned = total_earned(settlement_db, worklog.id)
        assert earned == Decimal("50.00")

    def test_total_earned_with_adjustments(self, settlement_db: Session):
        """Test total_earned includes adjustments."""
        user = User(
            id=uuid4(),
            email="calc.adjust@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        # 100 minutes → 50.00
        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=100
        )
        settlement_db.add(segment)
        settlement_db.commit()

        # Add 10.50 adjustment
        adjustment = Adjustment(
            id=uuid4(),
            worklog_id=worklog.id,
            amount=Decimal("10.50"),
            reason="Bonus",
        )
        settlement_db.add(adjustment)
        settlement_db.commit()

        earned = total_earned(settlement_db, worklog.id)
        assert earned == Decimal("60.50")

    def test_total_earned_with_multiple_segments_and_adjustments(
        self, settlement_db: Session
    ):
        """Test total_earned with multiple segments and adjustments."""
        user = User(
            id=uuid4(),
            email="calc.multi@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        # Add 3 segments: 60 + 80 + 40 = 180 minutes → 90.00
        for minutes in [60, 80, 40]:
            segment = TimeSegment(
                id=uuid4(), worklog_id=worklog.id, minutes=minutes
            )
            settlement_db.add(segment)
        settlement_db.commit()

        # Add 2 adjustments: 5.00 + (-2.50) = 2.50
        for amount, reason in [
            (Decimal("5.00"), "Bonus"),
            (Decimal("-2.50"), "Penalty"),
        ]:
            adjustment = Adjustment(
                id=uuid4(),
                worklog_id=worklog.id,
                amount=amount,
                reason=reason,
            )
            settlement_db.add(adjustment)
        settlement_db.commit()

        earned = total_earned(settlement_db, worklog.id)
        assert earned == Decimal("92.50")

    def test_total_earned_empty_worklog(self, settlement_db: Session):
        """Test total_earned for worklog with no segments or adjustments."""
        user = User(
            id=uuid4(),
            email="calc.empty@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        earned = total_earned(settlement_db, worklog.id)
        assert earned == Decimal("0")

    def test_total_remitted_with_success_remittances(
        self, settlement_db: Session
    ):
        """Test total_remitted counts only SUCCESS remittances."""
        user = User(
            id=uuid4(),
            email="remit.success@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        # Create SUCCESS remittance with 30.00
        remittance = Remittance(
            id=uuid4(),
            user_id=user.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            status=RemittanceStatus.SUCCESS,
        )
        settlement_db.add(remittance)
        settlement_db.commit()

        item = RemittanceItem(
            id=uuid4(),
            remittance_id=remittance.id,
            worklog_id=worklog.id,
            amount=Decimal("30.00"),
        )
        settlement_db.add(item)
        settlement_db.commit()

        remitted = total_remitted(settlement_db, worklog.id)
        assert remitted == Decimal("30.00")

    def test_total_remitted_ignores_failed_remittances(
        self, settlement_db: Session
    ):
        """Test total_remitted ignores FAILED and CANCELLED remittances."""
        user = User(
            id=uuid4(),
            email="remit.failed@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        # Create FAILED remittance
        remittance_failed = Remittance(
            id=uuid4(),
            user_id=user.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            status=RemittanceStatus.FAILED,
        )
        settlement_db.add(remittance_failed)
        settlement_db.commit()

        item_failed = RemittanceItem(
            id=uuid4(),
            remittance_id=remittance_failed.id,
            worklog_id=worklog.id,
            amount=Decimal("20.00"),
        )
        settlement_db.add(item_failed)
        settlement_db.commit()

        # Create CANCELLED remittance
        remittance_cancelled = Remittance(
            id=uuid4(),
            user_id=user.id,
            period_start=date(2024, 2, 1),
            period_end=date(2024, 2, 29),
            status=RemittanceStatus.CANCELLED,
        )
        settlement_db.add(remittance_cancelled)
        settlement_db.commit()

        item_cancelled = RemittanceItem(
            id=uuid4(),
            remittance_id=remittance_cancelled.id,
            worklog_id=worklog.id,
            amount=Decimal("15.00"),
        )
        settlement_db.add(item_cancelled)
        settlement_db.commit()

        remitted = total_remitted(settlement_db, worklog.id)
        assert remitted == Decimal("0")

    def test_total_remitted_empty_worklog(self, settlement_db: Session):
        """Test total_remitted for worklog with no remittances."""
        user = User(
            id=uuid4(),
            email="remit.empty@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        remitted = total_remitted(settlement_db, worklog.id)
        assert remitted == Decimal("0")

    def test_payable_amount_calculation(self, settlement_db: Session):
        """Test payable_amount = earned - remitted."""
        user = User(
            id=uuid4(),
            email="payable@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        # Earned: 100 minutes = 50.00
        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=100
        )
        settlement_db.add(segment)
        settlement_db.commit()

        # Remitted: 20.00 (SUCCESS)
        remittance = Remittance(
            id=uuid4(),
            user_id=user.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            status=RemittanceStatus.SUCCESS,
        )
        settlement_db.add(remittance)
        settlement_db.commit()

        item = RemittanceItem(
            id=uuid4(),
            remittance_id=remittance.id,
            worklog_id=worklog.id,
            amount=Decimal("20.00"),
        )
        settlement_db.add(item)
        settlement_db.commit()

        payable = payable_amount(settlement_db, worklog.id)
        assert payable == Decimal("30.00")

    def test_payable_amount_zero_when_fully_remitted(
        self, settlement_db: Session
    ):
        """Test payable_amount is zero when fully remitted."""
        user = User(
            id=uuid4(),
            email="payable.zero@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        # Earned: 50.00
        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=100
        )
        settlement_db.add(segment)
        settlement_db.commit()

        # Remitted: 50.00 (matches earned)
        remittance = Remittance(
            id=uuid4(),
            user_id=user.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            status=RemittanceStatus.SUCCESS,
        )
        settlement_db.add(remittance)
        settlement_db.commit()

        item = RemittanceItem(
            id=uuid4(),
            remittance_id=remittance.id,
            worklog_id=worklog.id,
            amount=Decimal("50.00"),
        )
        settlement_db.add(item)
        settlement_db.commit()

        payable = payable_amount(settlement_db, worklog.id)
        assert payable == Decimal("0")


class TestSettlementAPI:
    """Test Settlement API endpoints."""

    def test_generate_remittances_endpoint_with_no_users(
        self, settlement_client: TestClient, settlement_db: Session
    ):
        """Test generate-remittances endpoint when no users exist."""
        response = settlement_client.post(
            "/api/v1/settlements/generate-remittances-for-all-users"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["generated"] == 0

    def test_generate_remittances_endpoint_with_unpayable_user(
        self, settlement_client: TestClient, settlement_db: Session
    ):
        """Test generate-remittances skips users with no payable amount."""
        user = User(
            id=uuid4(),
            email="unpayable@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        response = settlement_client.post(
            "/api/v1/settlements/generate-remittances-for-all-users"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["generated"] == 0

    def test_generate_remittances_endpoint_with_payable_user(
        self, settlement_client: TestClient, settlement_db: Session
    ):
        """Test generate-remittances creates remittance for payable user."""
        user = User(
            id=uuid4(),
            email="payable.user@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        # Add time segment so user has payable amount
        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=100
        )
        settlement_db.add(segment)
        settlement_db.commit()

        response = settlement_client.post(
            "/api/v1/settlements/generate-remittances-for-all-users"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["generated"] == 1
        assert data["status"] == "success"

    def test_list_all_worklogs_endpoint_empty(
        self, settlement_client: TestClient, settlement_db: Session
    ):
        """Test list-all-worklogs when no worklogs exist."""
        response = settlement_client.get(
            "/api/v1/settlements/list-all-worklogs"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["data"] == []

    def test_list_all_worklogs_endpoint_all_unremitted(
        self, settlement_client: TestClient, settlement_db: Session
    ):
        """Test list-all-worklogs returns unremitted worklogs by default."""
        user = User(
            id=uuid4(),
            email="list.user@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=100
        )
        settlement_db.add(segment)
        settlement_db.commit()

        response = settlement_client.get(
            "/api/v1/settlements/list-all-worklogs"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["data"]) == 1
        assert data["data"][0]["remittance_status"] == "UNREMITTED"
        assert data["data"][0]["amount"] == "50.00"

    def test_list_all_worklogs_filter_unremitted(
        self, settlement_client: TestClient, settlement_db: Session
    ):
        """Test list-all-worklogs filters by UNREMITTED status."""
        user = User(
            id=uuid4(),
            email="filter.user@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=100
        )
        settlement_db.add(segment)
        settlement_db.commit()

        response = settlement_client.get(
            "/api/v1/settlements/list-all-worklogs?remittanceStatus=UNREMITTED"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

    def test_list_all_worklogs_filter_remitted(
        self, settlement_client: TestClient, settlement_db: Session
    ):
        """Test list-all-worklogs filters by REMITTED status."""
        user = User(
            id=uuid4(),
            email="remitted.user@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        segment = TimeSegment(
            id=uuid4(), worklog_id=worklog.id, minutes=100
        )
        settlement_db.add(segment)
        settlement_db.commit()

        remittance = Remittance(
            id=uuid4(),
            user_id=user.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            status=RemittanceStatus.SUCCESS,
        )
        settlement_db.add(remittance)
        settlement_db.commit()

        item = RemittanceItem(
            id=uuid4(),
            remittance_id=remittance.id,
            worklog_id=worklog.id,
            amount=Decimal("50.00"),
        )
        settlement_db.add(item)
        settlement_db.commit()

        response = settlement_client.get(
            "/api/v1/settlements/list-all-worklogs?remittanceStatus=REMITTED"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["data"][0]["remittance_status"] == "REMITTED"

    def test_list_all_worklogs_invalid_filter(
        self, settlement_client: TestClient
    ):
        """Test list-all-worklogs rejects invalid status filters."""
        response = settlement_client.get(
            "/api/v1/settlements/list-all-worklogs?remittanceStatus=INVALID"
        )

        assert response.status_code == 422

    def test_remittance_model_relationships(
        self, settlement_db: Session
    ):
        """Test Remittance model relationships and cascading."""
        user = User(
            id=uuid4(),
            email="remittance.model@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        remittance = Remittance(
            id=uuid4(),
            user_id=user.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            status=RemittanceStatus.SUCCESS,
        )
        settlement_db.add(remittance)
        settlement_db.commit()

        item = RemittanceItem(
            id=uuid4(),
            remittance_id=remittance.id,
            worklog_id=worklog.id,
            amount=Decimal("50.00"),
        )
        settlement_db.add(item)
        settlement_db.commit()
        settlement_db.refresh(remittance)

        assert len(remittance.items) == 1
        assert remittance.items[0].amount == Decimal("50.00")

    def test_remittance_item_cascade_delete(self, settlement_db: Session):
        """Test RemittanceItems are deleted when Remittance is deleted."""
        user = User(
            id=uuid4(),
            email="item.cascade@example.com",
            hashed_password="hashed_pwd",
        )
        settlement_db.add(user)
        settlement_db.commit()

        worklog = WorkLog(id=uuid4(), user_id=user.id)
        settlement_db.add(worklog)
        settlement_db.commit()

        remittance = Remittance(
            id=uuid4(),
            user_id=user.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            status=RemittanceStatus.SUCCESS,
        )
        settlement_db.add(remittance)
        settlement_db.commit()

        item = RemittanceItem(
            id=uuid4(),
            remittance_id=remittance.id,
            worklog_id=worklog.id,
            amount=Decimal("50.00"),
        )
        settlement_db.add(item)
        settlement_db.commit()

        item_id = item.id
        settlement_db.delete(remittance)
        settlement_db.commit()

        deleted = settlement_db.get(RemittanceItem, item_id)
        assert deleted is None
