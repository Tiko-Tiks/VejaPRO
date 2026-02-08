import os
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.main import app
from app.models.project import (
    AuditLog,
    Base,
    Payment,
    Project,
    User,
)


class FinanceLedgerTests(unittest.TestCase):
    """Tests for Finance Ledger V1.0 (Phase 1): ledger CRUD, reverse, summary."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="ADMIN")

        def override_get_current_user():
            return self.current_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _create_project(self, status="DRAFT"):
        db = self.SessionLocal()
        project = Project(client_info={"client_id": "client-1"}, status=status)
        db.add(project)
        db.commit()
        db.refresh(project)
        db.close()
        return project

    def _create_user(self, role="ADMIN"):
        db = self.SessionLocal()
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            role=role,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.close()
        return user

    def _create_payment(self, project_id, payment_type="DEPOSIT", amount=100.0, status="SUCCEEDED"):
        db = self.SessionLocal()
        payment = Payment(
            project_id=project_id,
            provider="manual",
            provider_event_id=f"evt-{uuid.uuid4()}",
            amount=amount,
            currency="EUR",
            payment_type=payment_type,
            status=status,
            payment_method="CASH",
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
        db.close()
        return payment

    # ------------------------------------------------------------------
    # Feature flag gating
    # ------------------------------------------------------------------

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "false"}, clear=False)
    def test_ledger_returns_404_when_disabled(self):
        resp = self.client.get("/api/v1/admin/finance/ledger")
        self.assertEqual(resp.status_code, 404)

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_ledger_accessible_when_enabled(self):
        resp = self.client.get("/api/v1/admin/finance/ledger")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["items"], [])
        self.assertFalse(data["has_more"])

    # ------------------------------------------------------------------
    # Ledger CRUD
    # ------------------------------------------------------------------

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_create_ledger_entry(self):
        project = self._create_project()
        resp = self.client.post(
            "/api/v1/admin/finance/ledger",
            json={
                "project_id": str(project.id),
                "entry_type": "EXPENSE",
                "category": "FUEL",
                "description": "Kuras pristatymui",
                "amount": 45.50,
                "currency": "EUR",
                "payment_method": "CASH",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["entry_type"], "EXPENSE")
        self.assertEqual(data["category"], "FUEL")
        self.assertEqual(data["amount"], 45.5)
        self.assertEqual(data["project_id"], str(project.id))

        # Verify audit log
        db = self.SessionLocal()
        logs = db.query(AuditLog).filter(AuditLog.action == "FINANCE_LEDGER_ENTRY_CREATED").all()
        self.assertEqual(len(logs), 1)
        db.close()

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_create_overhead_entry_no_project(self):
        resp = self.client.post(
            "/api/v1/admin/finance/ledger",
            json={
                "entry_type": "EXPENSE",
                "category": "INSURANCE",
                "description": "Draudimas",
                "amount": 200.00,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["project_id"])
        self.assertEqual(data["category"], "INSURANCE")

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_create_entry_rejects_zero_amount(self):
        resp = self.client.post(
            "/api/v1/admin/finance/ledger",
            json={
                "entry_type": "EXPENSE",
                "category": "FUEL",
                "amount": 0,
            },
        )
        self.assertEqual(resp.status_code, 422)

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_list_ledger_entries_with_filter(self):
        project = self._create_project()
        # Create 2 entries
        self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"project_id": str(project.id), "entry_type": "EXPENSE", "category": "FUEL", "amount": 10.0},
        )
        self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"project_id": str(project.id), "entry_type": "TAX", "category": "TAXES", "amount": 20.0},
        )

        # List all
        resp = self.client.get("/api/v1/admin/finance/ledger")
        self.assertEqual(len(resp.json()["items"]), 2)

        # Filter by entry_type
        resp = self.client.get("/api/v1/admin/finance/ledger", params={"entry_type": "TAX"})
        items = resp.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["entry_type"], "TAX")

        # Filter by project_id
        resp = self.client.get("/api/v1/admin/finance/ledger", params={"project_id": str(project.id)})
        self.assertEqual(len(resp.json()["items"]), 2)

    # ------------------------------------------------------------------
    # Reverse (forward-only corrections)
    # ------------------------------------------------------------------

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_reverse_entry(self):
        project = self._create_project()
        create_resp = self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"project_id": str(project.id), "entry_type": "EXPENSE", "category": "FUEL", "amount": 100.0},
        )
        entry_id = create_resp.json()["id"]

        reverse_resp = self.client.post(
            f"/api/v1/admin/finance/ledger/{entry_id}/reverse",
            json={"reason": "Klaidingas įrašas"},
        )
        self.assertEqual(reverse_resp.status_code, 200)
        data = reverse_resp.json()
        self.assertEqual(data["entry_type"], "ADJUSTMENT")
        self.assertEqual(data["reverses_entry_id"], entry_id)
        self.assertEqual(data["amount"], 100.0)

        # Verify audit
        db = self.SessionLocal()
        logs = db.query(AuditLog).filter(AuditLog.action == "FINANCE_LEDGER_ENTRY_REVERSED").all()
        self.assertEqual(len(logs), 1)
        db.close()

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_double_reverse_rejected(self):
        create_resp = self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"entry_type": "EXPENSE", "category": "FUEL", "amount": 50.0},
        )
        entry_id = create_resp.json()["id"]

        # First reverse OK
        resp1 = self.client.post(
            f"/api/v1/admin/finance/ledger/{entry_id}/reverse",
            json={"reason": "Klaida"},
        )
        self.assertEqual(resp1.status_code, 200)

        # Second reverse → 400
        resp2 = self.client.post(
            f"/api/v1/admin/finance/ledger/{entry_id}/reverse",
            json={"reason": "Dar kartą"},
        )
        self.assertEqual(resp2.status_code, 400)

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_reverse_nonexistent_entry(self):
        fake_id = str(uuid.uuid4())
        resp = self.client.post(
            f"/api/v1/admin/finance/ledger/{fake_id}/reverse",
            json={"reason": "Neegzistuoja"},
        )
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Profit calculation / summary
    # ------------------------------------------------------------------

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_project_finance_summary(self):
        project = self._create_project()
        pid = str(project.id)

        # Income: 2 payments
        self._create_payment(project.id, "DEPOSIT", 500.0)
        self._create_payment(project.id, "FINAL", 1000.0)

        # Expenses: 2 entries
        self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"project_id": pid, "entry_type": "EXPENSE", "category": "MATERIALS", "amount": 200.0},
        )
        self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"project_id": pid, "entry_type": "TAX", "category": "TAXES", "amount": 50.0},
        )

        resp = self.client.get(f"/api/v1/admin/finance/projects/{pid}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_income"], 1500.0)
        self.assertEqual(data["total_expenses"], 250.0)
        self.assertEqual(data["net_expenses"], 250.0)
        self.assertEqual(data["profit"], 1250.0)

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_project_profit_with_reversal(self):
        project = self._create_project()
        pid = str(project.id)

        self._create_payment(project.id, "DEPOSIT", 1000.0)

        # Expense
        create_resp = self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"project_id": pid, "entry_type": "EXPENSE", "category": "FUEL", "amount": 300.0},
        )
        entry_id = create_resp.json()["id"]

        # Reverse that expense
        self.client.post(
            f"/api/v1/admin/finance/ledger/{entry_id}/reverse",
            json={"reason": "Klaida"},
        )

        resp = self.client.get(f"/api/v1/admin/finance/projects/{pid}")
        data = resp.json()
        # net_expenses = 300 (EXPENSE) - 300 (ADJUSTMENT reversal) = 0
        self.assertEqual(data["total_expenses"], 300.0)
        self.assertEqual(data["net_expenses"], 0.0)
        self.assertEqual(data["profit"], 1000.0)

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_period_summary(self):
        project = self._create_project()
        self._create_payment(project.id, "DEPOSIT", 500.0)
        self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"project_id": str(project.id), "entry_type": "EXPENSE", "category": "MATERIALS", "amount": 100.0},
        )

        resp = self.client.get("/api/v1/admin/finance/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_income"], 500.0)
        self.assertEqual(data["total_expenses"], 100.0)
        self.assertEqual(data["profit"], 400.0)
        self.assertGreaterEqual(data["project_count"], 1)

    # ------------------------------------------------------------------
    # Vendor Rules
    # ------------------------------------------------------------------

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_vendor_rule_crud(self):
        # Create
        resp = self.client.post(
            "/api/v1/admin/finance/vendor-rules",
            json={
                "vendor_pattern": "SHELL FUEL",
                "default_category": "FUEL",
                "default_entry_type": "EXPENSE",
            },
        )
        self.assertEqual(resp.status_code, 200)
        rule = resp.json()
        self.assertEqual(rule["vendor_pattern"], "SHELL FUEL")
        self.assertTrue(rule["is_active"])

        # List
        resp = self.client.get("/api/v1/admin/finance/vendor-rules")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["items"]), 1)

        # Duplicate → 400
        resp = self.client.post(
            "/api/v1/admin/finance/vendor-rules",
            json={"vendor_pattern": "SHELL FUEL", "default_category": "FUEL"},
        )
        self.assertEqual(resp.status_code, 400)

        # Delete (soft)
        resp = self.client.delete(f"/api/v1/admin/finance/vendor-rules/{rule['id']}")
        self.assertEqual(resp.status_code, 200)

        # After delete: list returns empty (soft-deleted)
        resp = self.client.get("/api/v1/admin/finance/vendor-rules")
        self.assertEqual(len(resp.json()["items"]), 0)

    # ------------------------------------------------------------------
    # RBAC: SUBCONTRACTOR can create entries, only ADMIN can reverse
    # ------------------------------------------------------------------

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_subcontractor_can_create_entry(self):
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="SUBCONTRACTOR")
        resp = self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"entry_type": "EXPENSE", "category": "FUEL", "amount": 25.0},
        )
        self.assertEqual(resp.status_code, 200)

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_subcontractor_cannot_reverse(self):
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="ADMIN")
        create_resp = self.client.post(
            "/api/v1/admin/finance/ledger",
            json={"entry_type": "EXPENSE", "category": "FUEL", "amount": 25.0},
        )
        entry_id = create_resp.json()["id"]

        # Switch to SUBCONTRACTOR
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="SUBCONTRACTOR")
        resp = self.client.post(
            f"/api/v1/admin/finance/ledger/{entry_id}/reverse",
            json={"reason": "Test"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_expert_cannot_access_ledger(self):
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="EXPERT")
        resp = self.client.get("/api/v1/admin/finance/ledger")
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
