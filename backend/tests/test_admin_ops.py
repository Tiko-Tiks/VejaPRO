import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.main import app
from app.models.project import Appointment, AuditLog, Base, CallRequest, Evidence, Payment, Project, ProjectScheduling
from app.services.admin_read_models import derive_client_key


class AdminOpsApiTests(unittest.TestCase):
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

        self._prev_ops = os.environ.get("ENABLE_ADMIN_OPS_V1")
        self._prev_calls = os.environ.get("ENABLE_CALL_ASSISTANT")

        os.environ["ENABLE_ADMIN_OPS_V1"] = "true"
        os.environ["ENABLE_CALL_ASSISTANT"] = "true"
        get_settings.cache_clear()

        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

        if self._prev_ops is None:
            os.environ.pop("ENABLE_ADMIN_OPS_V1", None)
        else:
            os.environ["ENABLE_ADMIN_OPS_V1"] = self._prev_ops

        if self._prev_calls is None:
            os.environ.pop("ENABLE_CALL_ASSISTANT", None)
        else:
            os.environ["ENABLE_CALL_ASSISTANT"] = self._prev_calls

        get_settings.cache_clear()

    def _set_ops_flag(self, enabled: bool) -> None:
        os.environ["ENABLE_ADMIN_OPS_V1"] = "true" if enabled else "false"
        get_settings.cache_clear()

    def _create_project(self, *, status: str = "DRAFT", updated_at: datetime | None = None) -> Project:
        db = self.SessionLocal()
        now = updated_at or datetime.now(timezone.utc)
        project = Project(
            client_info={"name": "Jonas", "email": "jonas@example.com", "phone": "+37061234567"},
            status=status,
            created_at=now,
            updated_at=now,
            total_price_client=199.99,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        db.close()
        return project

    def _create_appointment(
        self,
        *,
        project_id: str | None,
        starts_at: datetime,
        ends_at: datetime,
        status: str = "CONFIRMED",
    ) -> Appointment:
        db = self.SessionLocal()
        hold_expires_at = None
        if status == "HELD":
            hold_expires_at = ends_at + timedelta(minutes=30)
        row = Appointment(
            project_id=project_id,
            call_request_id=None,
            resource_id=None,
            visit_type="PRIMARY",
            starts_at=starts_at,
            ends_at=ends_at,
            status=status,
            lock_level=0,
            hold_expires_at=hold_expires_at,
            weather_class="MIXED",
            row_version=1,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        db.close()
        return row

    def test_ops_routes_feature_flag_guard(self):
        self._set_ops_flag(False)

        day_resp = self.client.get("/api/v1/admin/ops/day/2026-02-13/plan")
        self.assertEqual(day_resp.status_code, 404)

        inbox_resp = self.client.get("/api/v1/admin/ops/inbox")
        self.assertEqual(inbox_resp.status_code, 404)
        card_resp = self.client.get("/api/v1/admin/ops/client/test-client/card")
        self.assertEqual(card_resp.status_code, 404)

        html_resp = self.client.get("/admin/client/test-client")
        self.assertEqual(html_resp.status_code, 404)

        project_html_resp = self.client.get(f"/admin/project/{uuid.uuid4()}?day=2026-02-13")
        self.assertEqual(project_html_resp.status_code, 404)

        archive_resp = self.client.get("/admin/archive")
        self.assertEqual(archive_resp.status_code, 404)

        self._set_ops_flag(True)
        day_resp_enabled = self.client.get("/api/v1/admin/ops/day/2026-02-13/plan")
        self.assertEqual(day_resp_enabled.status_code, 200)

        html_resp_enabled = self.client.get("/admin/client/test-client")
        self.assertEqual(html_resp_enabled.status_code, 200)

        project_html_resp_enabled = self.client.get(f"/admin/project/{uuid.uuid4()}?day=2026-02-13")
        self.assertEqual(project_html_resp_enabled.status_code, 200)

        archive_resp_enabled = self.client.get("/admin/archive")
        self.assertEqual(archive_resp_enabled.status_code, 200)
        self.assertIn("Archyvas", archive_resp_enabled.text)
        self.assertIn("archiveMode", archive_resp_enabled.text)
        self.assertIn("archiveStatusFilter", archive_resp_enabled.text)

    def test_day_plan_sums_minutes_uses_limits_and_sorts(self):
        self._set_ops_flag(True)

        day = datetime(2026, 2, 13, 8, 0, tzinfo=timezone.utc)
        project = self._create_project(status="PAID", updated_at=day - timedelta(hours=1))

        db = self.SessionLocal()
        db.add(ProjectScheduling(project_id=project.id, estimated_duration_min=180))
        db.commit()
        db.close()

        # Later appointment created first to ensure API sort is by starts_at asc.
        self._create_appointment(
            project_id=str(project.id),
            starts_at=day + timedelta(hours=4),
            ends_at=day + timedelta(hours=5),
            status="CONFIRMED",
        )
        self._create_appointment(
            project_id=str(project.id),
            starts_at=day + timedelta(hours=1),
            ends_at=day + timedelta(hours=2),
            status="CONFIRMED",
        )

        resp = self.client.get("/api/v1/admin/ops/day/2026-02-13/plan", params={"limit": 50})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["summary"]["date"], "2026-02-13")
        self.assertEqual(data["summary"]["jobs_count"], 2)
        # Both rows use estimated duration 180 min from project_scheduling.
        self.assertEqual(data["summary"]["total_minutes"], 360)
        self.assertEqual(len(data["items"]), 2)

        starts = [item["start"] for item in data["items"]]
        self.assertLess(starts[0], starts[1])

        limited = self.client.get("/api/v1/admin/ops/day/2026-02-13/plan", params={"limit": 1})
        self.assertEqual(limited.status_code, 200)
        self.assertEqual(len(limited.json()["items"]), 1)

    def test_ops_endpoints_require_admin_role(self):
        self._set_ops_flag(True)
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="SUBCONTRACTOR")

        day_resp = self.client.get("/api/v1/admin/ops/day/2026-02-13/plan")
        self.assertEqual(day_resp.status_code, 403)

        inbox_resp = self.client.get("/api/v1/admin/ops/inbox")
        self.assertEqual(inbox_resp.status_code, 403)
        card_resp = self.client.get("/api/v1/admin/ops/client/test-client/card")
        self.assertEqual(card_resp.status_code, 403)

    def test_inbox_task_ids_are_deterministic_and_sorted(self):
        self._set_ops_flag(True)

        now = datetime(2026, 2, 13, 9, 0, tzinfo=timezone.utc)
        project = self._create_project(status="DRAFT", updated_at=now)
        self._create_appointment(
            project_id=str(project.id),
            starts_at=now + timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
            status="HELD",
        )

        db = self.SessionLocal()
        db.add(
            CallRequest(
                name="Petras",
                phone="+37060000000",
                email="petras@example.com",
                status="NEW",
                source="public",
                preferred_channel="email",
                intake_state={},
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        db.close()

        resp1 = self.client.get("/api/v1/admin/ops/inbox", params={"limit": 30})
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()

        self.assertLessEqual(len(data1["items"]), 30)
        self.assertGreaterEqual(len(data1["items"]), 2)

        # Sorted by priority ascending.
        priorities = [item["priority"] for item in data1["items"]]
        self.assertEqual(priorities, sorted(priorities))

        resp2 = self.client.get("/api/v1/admin/ops/inbox", params={"limit": 30})
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()

        ids1 = [item["task_id"] for item in data1["items"]]
        ids2 = [item["task_id"] for item in data2["items"]]
        self.assertEqual(ids1, ids2)

        resp_limited = self.client.get("/api/v1/admin/ops/inbox", params={"limit": 1})
        self.assertEqual(resp_limited.status_code, 200)
        self.assertEqual(len(resp_limited.json()["items"]), 1)

    def test_project_day_action_creates_audit_row(self):
        self._set_ops_flag(True)
        project = self._create_project(status="PAID", updated_at=datetime(2026, 2, 13, 9, 0, tzinfo=timezone.utc))

        resp = self.client.post(
            f"/api/v1/admin/ops/project/{project.id}/day-action",
            json={"day": "2026-02-13", "action": "check_in", "note": "Arrived on site"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])

        db = self.SessionLocal()
        row = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "project",
                AuditLog.entity_id == project.id,
                AuditLog.action == "ADMIN_DAY_CHECK_IN",
            )
            .first()
        )
        db.close()
        self.assertIsNotNone(row)

    def test_proposal_action_requires_admin_and_honors_flag(self):
        self._set_ops_flag(False)
        off_resp = self.client.post(
            "/api/v1/admin/ops/client/abc/proposal-action",
            json={"action": "approve", "note": ""},
        )
        self.assertEqual(off_resp.status_code, 404)

        self._set_ops_flag(True)
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="SUBCONTRACTOR")
        denied = self.client.post(
            "/api/v1/admin/ops/client/abc/proposal-action",
            json={"action": "approve", "note": ""},
        )
        self.assertEqual(denied.status_code, 403)

    def test_proposal_action_creates_system_audit(self):
        self._set_ops_flag(True)
        resp = self.client.post(
            "/api/v1/admin/ops/client/demo-client/proposal-action",
            json={"action": "escalate", "note": "Need supervisor", "project_id": None},
        )
        self.assertEqual(resp.status_code, 200)

        db = self.SessionLocal()
        row = db.query(AuditLog).filter(AuditLog.action == "ADMIN_CLIENT_PROPOSAL_ACTION").first()
        db.close()
        self.assertIsNotNone(row)

    def test_client_card_batched_payload_honors_limits_and_masks_pii(self):
        self._set_ops_flag(True)
        now = datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc)

        project_a = self._create_project(status="CERTIFIED", updated_at=now)
        project_b = self._create_project(status="PAID", updated_at=now - timedelta(hours=1))
        client_key, _ = derive_client_key(project_a.client_info)

        db = self.SessionLocal()
        db.add_all(
            [
                Payment(
                    project_id=project_a.id,
                    provider="stripe",
                    amount=100.00,
                    currency="EUR",
                    payment_type="DEPOSIT",
                    status="SUCCEEDED",
                    payment_method="manual",
                    received_at=now - timedelta(days=1),
                    created_at=now - timedelta(days=1),
                ),
                Payment(
                    project_id=project_b.id,
                    provider="stripe",
                    amount=299.00,
                    currency="EUR",
                    payment_type="FINAL",
                    status="SUCCEEDED",
                    payment_method="manual",
                    received_at=now - timedelta(hours=2),
                    created_at=now - timedelta(hours=2),
                ),
                Evidence(
                    project_id=project_a.id,
                    file_url="https://cdn.example.com/evidence/a.jpg",
                    thumbnail_url="https://cdn.example.com/evidence/a-thumb.jpg",
                    medium_url="https://cdn.example.com/evidence/a-med.jpg",
                    category="BEFORE",
                    uploaded_at=now - timedelta(minutes=20),
                    created_at=now - timedelta(minutes=20),
                ),
                Evidence(
                    project_id=project_b.id,
                    file_url="https://cdn.example.com/evidence/b.jpg",
                    thumbnail_url="https://cdn.example.com/evidence/b-thumb.jpg",
                    medium_url="https://cdn.example.com/evidence/b-med.jpg",
                    category="AFTER",
                    uploaded_at=now - timedelta(minutes=10),
                    created_at=now - timedelta(minutes=10),
                ),
                AuditLog(
                    entity_type="project",
                    entity_id=project_a.id,
                    action="TEST_AUDIT_A",
                    actor_type="ADMIN",
                    actor_id=self.current_user.id,
                    timestamp=now - timedelta(minutes=3),
                ),
                AuditLog(
                    entity_type="project",
                    entity_id=project_b.id,
                    action="TEST_AUDIT_B",
                    actor_type="ADMIN",
                    actor_id=self.current_user.id,
                    timestamp=now - timedelta(minutes=2),
                ),
                CallRequest(
                    name="Jonas",
                    phone="+37061234567",
                    email="jonas@example.com",
                    status="NEW",
                    source="public",
                    preferred_channel="email",
                    intake_state={},
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=1),
                ),
            ]
        )
        db.commit()
        db.close()

        resp = self.client.get(
            f"/api/v1/admin/ops/client/{client_key}/card",
            params={
                "projects_limit": 1,
                "payments_limit": 1,
                "calls_limit": 1,
                "photos_limit": 1,
                "timeline_limit": 1,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["summary"]["client_key"], client_key)
        self.assertEqual(data["summary"]["total_projects"], 2)
        self.assertEqual(len(data["projects"]), 1)
        self.assertEqual(len(data["payments"]), 1)
        self.assertEqual(len(data["calls"]), 1)
        self.assertEqual(len(data["photos"]), 1)
        self.assertEqual(len(data["timeline"]), 1)

        contact_masked = data["calls"][0]["data"]["contact_masked"]
        self.assertNotIn("jonas@example.com", contact_masked)
        self.assertNotIn("+37061234567", contact_masked)
        self.assertIn("***", contact_masked)


if __name__ == "__main__":
    unittest.main()
