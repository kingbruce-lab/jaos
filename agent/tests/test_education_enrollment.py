import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, EducationStudent, EducationAssessment, EducationCohort, EducationStaff
from app.auth import hash_password
from app.project_system import project_delete_rate_limiter
from test_education_system import setup, cohort_payload, entry_payload


def student_payload(**changes):
    return {"request_id": str(uuid4()), "registration_date": "2026-09-12", "name": "测试学员",
        "gender": "女", "age": 17, "identity_number": "110101200901010012", "phone": "13800000001",
        "game": "王者荣耀", "course_period": "8_days", "study_start": "2026-10-01", "accommodation_days": 7,
        "room_type": "两人间", "fee_notes": "测试费用", "fees": [
            {"category": "学费", "detail": "课程学费", "receivable": "3000.50", "cost": "500"},
            {"category": "住宿费", "detail": "两人间", "receivable": "0", "cost": "350"},
            {"category": "活动经费", "detail": "团建活动", "receivable": "0", "cost": "60.25"}],
        "received": "2000.25", "notes": "测试备注", **changes}


def make_cohort(client):
    response = client.post("/v1/pm/education/cohorts", json=cohort_payload())
    assert response.status_code == 200
    return f"/v1/pm/education/cohorts/{response.json()['id']}"


def test_registration_fees_arrears_privacy_and_combined_totals(setup):
    client, db, users, actor = setup
    path = make_cohort(client)
    payload = student_payload()
    result = client.post(path + "/students", json=payload)
    assert result.status_code == 200, result.text
    student_path = path + "/students/" + result.json()["id"]
    assert client.post(path + "/students", json=payload).json() == result.json()
    detail = client.get(student_path).json()
    assert detail["study_end"] == "2026-10-08"
    assert detail["receivable"] == "3000.50"
    assert detail["cost"] == "910.25"
    assert detail["arrears"] == "1000.25"
    assert "identity_number" not in detail and "phone" not in detail
    for route in (path, path + "/students", student_path):
        text = client.get(route).text
        assert payload["identity_number"] not in text and payload["phone"] not in text
    assert payload["identity_number"] not in "".join(db.scalars(select(AuditLog.details_json)).all())
    revealed = client.post(student_path + "/identity")
    assert revealed.status_code == 200
    assert revealed.headers["cache-control"] == "no-store"
    assert revealed.json()["phone"] == payload["phone"]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "education_student_identity_viewed"))
    update = {key: value for key, value in payload.items() if key != "request_id"}
    update.update(version=1, received="3900.50", identity_number=None, phone=None, course_period="3_months")
    assert client.patch(student_path, json=update).status_code == 200
    assert client.patch(student_path, json=update).status_code == 409
    detail = client.get(student_path).json()
    assert detail["study_end"] == "2026-12-26"
    assert detail["arrears"] == "0.00" and detail["overpayment"] == "900.00"
    assert client.post(student_path + "/identity").json()["phone"] == payload["phone"]
    second = client.post(path + "/students", json=student_payload(name="另一测试学员", received="0"))
    assert second.status_code == 200
    summary = client.get(path + "/students?limit=1").json()
    assert summary["has_more"] and len(summary["items"]) == 1
    assert summary["summary"]["arrears"] == "3000.50"  # A surplus never cancels another student's debt.
    assert client.post(path + "/entries", json=entry_payload(direction="expense", amount="100", purpose="公共场地费")).status_code == 200
    cohort = client.get(path).json()
    assert cohort["effective_student_count"] == 2
    assert cohort["income"] == "3900.50"
    assert cohort["expense"] == "1920.50"
    assert cohort["expected_income"] == "6001.00"
    overview = client.get("/v1/pm/education/cohorts").json()
    assert overview["summary"]["student_count"] == 2
    assert overview["summary"]["income"] == "3900.50"
    assert overview["enrollment_summary"]["arrears"] == "3000.50"
    update.update(version=2, identity_number="", phone="")
    assert client.patch(student_path, json=update).status_code == 200
    assert client.post(student_path + "/identity").json() == {"identity_number": "", "phone": "", "guardian_phone": ""}


def test_enrollment_staff_scope_and_finance_identity_protection(setup):
    client, db, users, actor = setup
    path = make_cohort(client)
    staff = client.post(path + "/staff", json={"request_id": str(uuid4()), "name": "测试教练", "role": "王者荣耀教师"})
    assert staff.status_code == 200
    staff_id = staff.json()["id"]
    fee = {"category": "人员成本", "detail": "王者荣耀教师", "staff_id": staff_id, "cost": "100"}
    result = client.post(path + "/students", json=student_payload(fees=[fee]))
    assert result.status_code == 200
    student_path = path + "/students/" + result.json()["id"]
    other_path = make_cohort(client)
    assert client.post(other_path + "/students", json=student_payload(fees=[fee])).status_code == 422
    assert client.post(other_path + "/entries", json=entry_payload(category="人员成本", detail="王者荣耀教师", staff_id=staff_id)).status_code == 422
    assert client.post(path + "/entries", json=entry_payload(category="人员成本", detail="王者荣耀教师", staff_id=staff_id)).status_code == 200
    actor[0] = users["finance"]
    assert client.get(student_path).status_code == 200
    assert client.post(student_path + "/identity").status_code == 403
    assert client.post(path + "/students", json=student_payload()).status_code == 403
    actor[0] = users["other"]
    for route in (path + "/students", student_path, path + "/staff"):
        assert client.get(route).status_code == 404
    assert client.post(student_path + "/identity").status_code == 404
    actor[0] = users["business"]
    assert client.get("/v1/pm/education/options").status_code == 403


def test_referral_commission_continuous_staff_and_student_staff_timeline(setup):
    client, db, *_ = setup
    path = make_cohort(client)
    options = client.get("/v1/pm/education/options").json()
    assert "状态恢复师" in options["staff_roles"]
    assert options["fee_details"]["推荐渠道提成费"] == ["推荐人提成", "渠道提成", "其他"]
    assert client.post(path + "/staff", json={"request_id": str(uuid4()), "name": "未注明教师", "role": "其他教师"}).status_code == 422
    teacher = client.post(path + "/staff", json={"request_id": str(uuid4()), "name": "王老师", "role": "其他教师", "note": "战术复盘"})
    recovery = client.post(path + "/staff", json={"request_id": str(uuid4()), "name": "李老师", "role": "状态恢复师", "note": "作息与心理状态"})
    assert teacher.status_code == recovery.status_code == 200
    roster = client.get(path + "/staff").json()["items"]
    assert {(item["name"], item["note"]) for item in roster} == {("王老师", "战术复盘"), ("李老师", "作息与心理状态")}
    assignments = [
        {"staff_id": teacher.json()["id"], "start_date": "2026-10-01", "end_date": "2026-10-08", "note": "主课"},
        {"staff_id": recovery.json()["id"], "start_date": "2026-10-02", "end_date": "2026-10-07", "note": "每日恢复"},
    ]
    payload = student_payload(referrer_name="张家长", referral_channel="家长转介绍", staff_assignments=assignments,
        fees=[{"category": "学费", "detail": "课程学费", "receivable": "3000", "cost": "0"},
              {"category": "推荐渠道提成费", "detail": "推荐人提成", "receivable": "0", "cost": "300", "note": "张家长10%"}])
    created = client.post(path + "/students", json=payload)
    assert created.status_code == 200, created.text
    detail = client.get(path + "/students/" + created.json()["id"]).json()
    assert detail["referrer_name"] == "张家长" and detail["referral_channel"] == "家长转介绍"
    assert [(item["name"], item["role"]) for item in detail["staff_assignments"]] == [("王老师", "其他教师"), ("李老师", "状态恢复师")]
    assert detail["cost"] == "300.00"
    listed = client.get(path + "/students").json()["items"][0]
    assert len(listed["staff_assignments"]) == 2
    ledger = client.get("/v1/pm/education/ledger?keyword=家长转介绍").json()
    assert ledger["items"][0]["referrer_name"] == "张家长"
    assert len(ledger["items"][0]["staff_assignments"]) == 2
    duplicated = {**payload, "request_id": str(uuid4()), "staff_assignments": assignments + [assignments[0]]}
    assert client.post(path + "/students", json=duplicated).status_code == 422
    outside = {**payload, "request_id": str(uuid4()), "staff_assignments": [{**assignments[0], "end_date": "2026-10-09"}]}
    assert client.post(path + "/students", json=outside).status_code == 422


@pytest.mark.parametrize("changes", [{"age": -1}, {"age": 2.5}, {"game": "其他"}, {"course_period": "one_year"},
    {"room_type": "三人间"}, {"accommodation_days": -1}, {"received": "NaN"}, {"identity_number": "invalid"},
    {"phone": "abc"}, {"fees": [{"category": "学费", "detail": "课程学费", "cost": "-1"}]},
    {"fees": [{"category": "住宿费", "detail": "两人间", "receivable": "1", "cost": "0"}]}, {"receivable": "1"}])
def test_invalid_student_fields(setup, changes):
    client, db, *_ = setup
    path = make_cohort(client)
    assert client.post(path + "/students", json=student_payload(**changes)).status_code == 422
    assert db.scalar(select(func.count(EducationStudent.id))) == 0


def assessment_payload(staff_id, **changes):
    return {"request_id": str(uuid4()), "stage": "baseline", "assessed_on": "2026-10-01", "evaluator_staff_id": staff_id,
        "stage_name": "入学基线", "scores": {"操作基础": 2, "团队协作": None}, "observations": "训练赛中需提醒后再执行团队指令",
        "goals": "能复述团队指令", "grouping": "基础组", **changes}


def test_remove_staff_preserves_history_and_blocks_new_assignments(setup):
    client, db, users, actor = setup
    owner = actor[0]
    path = make_cohort(client)
    staff_id = client.post(path + "/staff", json={"request_id": str(uuid4()), "name": "历史教练", "role": "助教"}).json()["id"]
    staff_path = path + "/staff/" + staff_id
    payload = student_payload(fees=[{"category": "人员成本", "detail": "助教", "staff_id": staff_id, "cost": "200"}])
    student_id = client.post(path + "/students", json=payload).json()["id"]
    student_path = path + "/students/" + student_id
    assessment = assessment_payload(staff_id, stage="final", final_summary="完成课程")
    assessment_id = client.post(student_path + "/assessments", json=assessment).json()["id"]
    entry = entry_payload(category="人员成本", detail="助教", staff_id=staff_id)
    entry_id = client.post(path + "/entries", json=entry).json()["id"]
    other_path = make_cohort(client)
    assert client.delete(other_path + "/staff/" + staff_id).status_code == 404
    actor[0] = users["finance"]
    assert client.delete(staff_path).status_code == 403
    actor[0] = users["other"]
    assert client.delete(staff_path).status_code == 404
    actor[0] = owner
    assert client.delete(staff_path).status_code == 200
    assert client.delete(staff_path).status_code == 200
    assert client.get(path + "/staff").json()["items"][0]["active"] is False
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "education_staff_removed")) == 1
    assert client.post(path + "/students", json={**payload, "request_id": str(uuid4())}).status_code == 422
    assert client.post(path + "/entries", json={**entry, "request_id": str(uuid4())}).status_code == 422
    assert client.post(student_path + "/assessments", json=assessment_payload(staff_id, stage="phase")).status_code == 422
    for target, original in ((student_path, payload), (path + "/entries/" + entry_id, entry), (student_path + "/assessments/" + assessment_id, assessment)):
        update = {key: value for key, value in original.items() if key != "request_id"}
        assert client.patch(target, json={**update, "version": 1}).status_code == 200
    assert "历史教练" in client.get(student_path + "/graduation-report").json()["text"]
    assert client.get(student_path).json()["cost"] == "200.00"


def test_founder_only_cohort_deletion_preserves_and_hides_related_records(setup):
    client, db, users, actor = setup
    path = make_cohort(client)
    name = client.get(path).json()["name"]
    teacher = actor[0]
    staff_id = client.post(path + "/staff", json={"request_id": str(uuid4()), "name": "教练", "role": "助教"}).json()["id"]
    student_id = client.post(path + "/students", json=student_payload()).json()["id"]
    student_path = path + "/students/" + student_id
    assessment_id = client.post(student_path + "/assessments", json=assessment_payload(staff_id)).json()["id"]
    payload = {"deletion_password": "Cohort-delete-2026", "confirm_name": name, "reason": "重复创建", "version": 1}
    assert client.get("/v1/pm/education/cohorts").json()["can_delete"] is False
    for key in ("teacher", "other", "finance", "business", "admin"):
        actor[0] = users[key]
        assert client.post(path + "/founder-delete", json=payload).status_code == 403
    users["admin"].organization_role = "management"
    users["admin"].confidentiality_ceiling = "L5"
    actor[0] = users["admin"]
    assert client.get("/v1/pm/education/cohorts").json()["can_delete"] is False
    assert client.post(path + "/founder-delete", json=payload).status_code == 403
    actor[0] = users["founder"]
    assert client.get("/v1/pm/education/cohorts").json()["can_delete"] is True
    assert client.post(path + "/founder-delete", json=payload).status_code == 409
    users["founder"].project_delete_password_hash = hash_password(payload["deletion_password"])
    db.commit()
    for changes in ({"confirm_name": "错误班期"}, {"version": 2}):
        assert client.post(path + "/founder-delete", json={**payload, **changes}).status_code == 409
    assert client.post(path + "/founder-delete", json={**payload, "deletion_password": "wrong"}).status_code == 403
    assert client.get(path).status_code == 200
    assert client.post(path + "/founder-delete", json=payload).status_code == 200
    assert client.post(path + "/founder-delete", json=payload).status_code == 404
    assert client.get("/v1/pm/education/cohorts").json()["summary"]["cohort_count"] == 0
    assert client.get("/v1/pm/education/cohorts").json()["summary"]["income"] == "0.00"
    for user in (users["founder"], teacher):
        actor[0] = user
        for target in (path, path + "/staff", path + "/entries", path + "/students", student_path, student_path + "/assessments", student_path + "/graduation-report"):
            assert client.get(target).status_code == 404
        assert client.post(path + "/entries", json=entry_payload()).status_code == 404
        assert client.post(student_path + "/identity").status_code == 404
    assert db.get(EducationCohort, path.split("/")[-1]).deleted_at is not None
    assert db.get(EducationStudent, student_id) is not None
    assert db.get(EducationStaff, staff_id) is not None
    assert db.get(EducationAssessment, assessment_id) is not None
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "education_cohort_deleted")).all()
    assert len(logs) == 1 and payload["deletion_password"] not in logs[0].details_json


def test_cohort_delete_password_attempts_are_limited(setup):
    client, db, users, actor = setup
    path = make_cohort(client)
    actor[0] = users["founder"]
    users["founder"].project_delete_password_hash = hash_password("Cohort-delete-2026")
    db.commit()
    project_delete_rate_limiter.reset()
    payload = {"deletion_password": "wrong", "confirm_name": client.get(path).json()["name"], "reason": "重复创建", "version": 1}
    try:
        responses = [client.post(path + "/founder-delete", json=payload) for _ in range(10)]
        assert responses[0].status_code == 403
        assert responses[-1].status_code == 429
        assert "retry-after" in responses[-1].headers
        assert client.get(path).status_code == 200
    finally:
        project_delete_rate_limiter.reset()


def test_assessment_lifecycle_report_and_future_expectations(setup):
    client, db, users, actor = setup
    path = make_cohort(client)
    staff_id = client.post(path + "/staff", json={"request_id": str(uuid4()), "name": "测试教练", "role": "助教"}).json()["id"]
    student = client.post(path + "/students", json=student_payload()).json()
    student_path = path + "/students/" + student["id"]
    assessment_path = student_path + "/assessments"
    assert client.get(student_path + "/graduation-report").status_code == 409
    payload = assessment_payload(staff_id)
    baseline = client.post(assessment_path, json=payload)
    assert baseline.status_code == 200, baseline.text
    assert client.post(assessment_path, json=payload).json() == baseline.json()
    assert client.post(assessment_path, json=assessment_payload(staff_id)).status_code == 409
    for index in (1, 2):
        assert client.post(assessment_path, json=assessment_payload(staff_id, stage="phase", stage_name=f"阶段{index}", stage_summary="观察到主动复盘")).status_code == 200
    assert client.post(assessment_path, json=assessment_payload(staff_id, stage="final", final_summary="独立执行基础配合", optimistic_outlook="有望稳定协作")).status_code == 422
    final = client.post(assessment_path, json=assessment_payload(staff_id, stage="final", final_summary="独立执行基础配合", parent_feedback="已能主动复述指令",
        conservative_outlook="保持每周训练有望巩固基础", optimistic_outlook="持续反馈下有望稳定协作", outlook_basis="依赖训练频率，迁移至正式比赛尚待观察"))
    assert final.status_code == 200
    records = client.get(assessment_path).json()
    assert len(records["items"]) == 4
    assert records["items"][0]["scores"]["团队协作"] is None
    report = client.get(student_path + "/graduation-report").json()["text"]
    for text in ("保守情景", "乐观情景", "阶段1", "阶段2", "未评估", "不承诺", "已能主动复述指令"):
        assert text in report
    assert "110101200901010012" not in report and "13800000001" not in report
    update = {key: value for key, value in payload.items() if key != "request_id"}
    update.update(version=1, observations="补充训练赛观察")
    assert client.patch(assessment_path + "/" + baseline.json()["id"], json=update).status_code == 200
    assert client.patch(assessment_path + "/" + baseline.json()["id"], json=update).status_code == 409
    actor[0] = users["other"]
    assert client.get(assessment_path).status_code == 404
    actor[0] = users["finance"]
    assert client.get(assessment_path).status_code == 403
    assert client.get(student_path + "/graduation-report").status_code == 403


@pytest.mark.parametrize("scores", [{"操作基础": 0}, {"操作基础": 6}, {"操作基础": 1.5}, {"智商": 5}, {"操作基础": True}])
def test_assessment_invalid_scores(setup, scores):
    client, db, *_ = setup
    path = make_cohort(client)
    staff_id = client.post(path + "/staff", json={"request_id": str(uuid4()), "name": "测试教练", "role": "助教"}).json()["id"]
    student_id = client.post(path + "/students", json=student_payload()).json()["id"]
    assert client.post(path + f"/students/{student_id}/assessments", json=assessment_payload(staff_id, scores=scores)).status_code == 422
    assert db.scalar(select(func.count(EducationAssessment.id))) == 0
