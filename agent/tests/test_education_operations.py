from uuid import uuid4

from sqlalchemy import func, select

from app.finance_system import _receivables_payables_payload
from app.models import (
    EducationCostAllocation, EducationCostAttachment, EducationCostDocument,
    EducationDailyLog, EducationMonthlySummary, EducationScheduleDay,
)
from test_education_enrollment import student_payload
from test_education_system import cohort_payload, setup


def _cohort(client):
    result = client.post("/v1/pm/education/cohorts", json=cohort_payload())
    assert result.status_code == 200
    return result.json()["id"]


def _student(client, cohort_id, **changes):
    result = client.post(
        f"/v1/pm/education/cohorts/{cohort_id}/students",
        json=student_payload(**changes),
    )
    assert result.status_code == 200, result.text
    return result.json()["id"]


def test_schedule_generation_is_idempotent_and_manual_changes_survive(setup):
    client, db, *_ = setup
    cohort_id = _cohort(client)
    path = f"/v1/pm/education/cohorts/{cohort_id}"
    student_id = _student(client, cohort_id, name="日报学员")
    staff_id = client.post(path + "/staff", json={
        "request_id": str(uuid4()), "name": "日报教师", "role": "王者荣耀教师",
    }).json()["id"]
    generated = client.post(path + "/schedule/generate")
    assert generated.status_code == 200
    assert generated.json() == {"created": 29, "total_days": 29}
    operations = client.get(path + "/operations").json()
    assert operations["schedule"]["summary"] == {"teaching": 25, "practice": 4, "rest": 0}
    assert operations["schedule"]["days"][6]["day_type"] == "practice"

    first = operations["schedule"]["days"][0]
    changed = client.patch(path + f"/schedule/{first['id']}", json={
        "day_type": "rest", "title": "入营调整", "notes": "办理入住", "version": first["version"],
        "report": {"instructor_ids": [staff_id], "student_ids": [student_id],
                   "attendance": "全员到齐", "lesson_objectives": "完成入学基线",
                   "lesson_content": "操作测试", "student_performance": "完成测试",
                   "special_achievement": True, "special_achievement_note": "反应速度提升",
                   "problem_flag": True, "problem_note": "设备延迟已处理"},
    })
    assert changed.status_code == 200
    assert client.post(path + "/schedule/generate").json() == {"created": 0, "total_days": 29}
    refreshed = client.get(path + "/operations").json()["schedule"]
    assert refreshed["days"][0]["day_type"] == "rest"
    assert refreshed["days"][0]["title"] == "入营调整"
    assert refreshed["days"][0]["report"]["instructor_ids"] == [staff_id]
    assert refreshed["days"][0]["report"]["student_ids"] == [student_id]
    assert refreshed["days"][0]["report"]["lesson_content"] == "操作测试"
    assert refreshed["days"][0]["report"]["special_achievement"] is True
    assert refreshed["days"][0]["report"]["problem_note"] == "设备延迟已处理"
    assert db.scalar(select(func.count(EducationScheduleDay.id))) == 29

    monthly = client.put(path + "/teaching-month-summaries/2026-10-01", json={
        "summary": "本教学月完成入学基线与六加一课程安排。", "achievements": "操作明显进步。",
        "problems": "设备延迟已解决。", "next_month_plan": "加强团队配合。", "version": 0,
    })
    assert monthly.status_code == 200, monthly.text
    assert client.put(path + "/teaching-month-summaries/2026-10-01", json={
        "summary": "并发旧版本", "achievements": "", "problems": "", "next_month_plan": "", "version": 0,
    }).status_code == 409
    assert client.put(path + "/teaching-month-summaries/2026-10-02", json={
        "summary": "错误周期", "achievements": "", "problems": "", "next_month_plan": "", "version": 0,
    }).status_code == 422
    monthly_view = client.get(path + "/operations").json()["schedule"]["monthly_summaries"]
    assert monthly_view[0]["period_start"] == "2026-10-01"
    assert monthly_view[0]["summary"].startswith("本教学月完成")
    assert db.scalar(select(func.count(EducationMonthlySummary.id))) == 1


def test_cost_document_calculates_total_and_posts_directly_to_ledger(setup):
    client, db, _, _ = setup
    cohort_id = _cohort(client)
    _student(client, cohort_id, name="学员甲")
    _student(client, cohort_id, name="学员乙", received="0")
    path = f"/v1/pm/education/cohorts/{cohort_id}"
    request_id = str(uuid4())
    payload = {
        "request_id": request_id,
        "occurred_on": "2026-10-03",
        "ended_on": "2026-10-09",
        "category": "饭费",
        "detail": "餐费套餐",
        "unit_price": "14.29",
        "vendor": "食堂",
        "document_no": "FP-001",
        "source_ref": "NAS/星曜/2026-10/FP-001.pdf",
        "note": "七天餐费",
    }
    created = client.post(path + "/cost-documents", json=payload)
    assert created.status_code == 200, created.text
    assert client.post(path + "/cost-documents", json=payload).json() == created.json()
    assert client.post(path + "/cost-documents", json={**payload, "unit_price": "14.00"}).status_code == 409

    operations = client.get(path + "/operations").json()
    assert operations["costs"]["source_total"] == "100.03"
    assert operations["costs"]["items"][0]["ended_on"] == "2026-10-09"
    assert operations["costs"]["items"][0]["unit_price"] == "14.29"
    assert operations["costs"]["items"][0]["quantity_days"] == 7
    assert operations["costs"]["ledger_total"] == "100.03"
    assert operations["costs"]["items"][0]["allocations"][0]["student_id"] is None
    assert client.get(path).json()["expense"] == "1920.53"
    cohort_summary = client.get("/v1/pm/education/cohorts").json()["summary"]
    assert cohort_summary["cost"] == "1920.53"
    assert cohort_summary["cash_expense"] == "0.00"
    ledger = client.get("/v1/pm/education/ledger?limit=100").json()
    assert ledger["summary"]["student_cost"] == "1820.50"
    assert ledger["summary"]["recorded_cost"] == "100.03"
    assert ledger["summary"]["cost"] == "1920.53"
    assert sorted(item["allocated_cost"] for item in ledger["items"]) == ["0.00", "0.00"]
    assert db.scalar(select(func.count(EducationCostDocument.id))) == 1
    assert db.scalar(select(func.count(EducationCostAllocation.id))) == 1


def test_cost_voucher_is_saved_downloaded_and_deleted_as_a_file(setup, tmp_path, monkeypatch):
    client, db, _, _ = setup
    monkeypatch.setattr("app.education_operations._attachment_root", lambda: tmp_path.resolve())
    cohort_id = _cohort(client)
    path = f"/v1/pm/education/cohorts/{cohort_id}"
    created = client.post(path + "/cost-documents", json={
        "request_id": str(uuid4()), "occurred_on": "2026-10-01", "ended_on": "2026-10-08",
        "category": "住宿费", "detail": "一人间", "unit_price": "100.00",
    })
    assert created.status_code == 200, created.text
    document_id = created.json()["id"]
    upload_path = path + f"/cost-documents/{document_id}/attachments"
    uploaded = client.post(upload_path, files={"file": ("住宿凭证.pdf", b"voucher-pdf", "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    attachment = uploaded.json()
    assert attachment["filename"] == "住宿凭证.pdf"
    assert attachment["size_bytes"] == 11
    operation_item = client.get(path + "/operations").json()["costs"]["items"][0]
    assert operation_item["attachments"][0]["id"] == attachment["id"]
    downloaded = client.get(upload_path + f"/{attachment['id']}")
    assert downloaded.status_code == 200
    assert downloaded.content == b"voucher-pdf"
    assert client.delete(upload_path + f"/{attachment['id']}").json() == {"deleted": True}
    assert db.scalar(select(func.count(EducationCostAttachment.id))) == 0
    assert not list(tmp_path.rglob("*.pdf"))


def test_daily_logs_are_scoped_and_hidden_from_finance(setup):
    client, db, users, actor = setup
    cohort_id = _cohort(client)
    student_id = _student(client, cohort_id)
    path = f"/v1/pm/education/cohorts/{cohort_id}"
    staff = client.post(path + "/staff", json={
        "request_id": str(uuid4()), "name": "班主任甲", "role": "班主任",
    }).json()
    client.post(path + "/schedule/generate")
    payload = {
        "request_id": str(uuid4()),
        "log_date": "2026-10-02",
        "staff_id": staff["id"],
        "log_type": "生活管理",
        "summary": "晚点名全员到齐，宿舍卫生完成检查。",
        "student_ids": [student_id],
        "follow_up": "明日复查空调关闭情况。",
    }
    result = client.post(path + "/daily-logs", json=payload)
    assert result.status_code == 200, result.text
    assert client.post(path + "/daily-logs", json=payload).json() == result.json()
    operations = client.get(path + "/operations").json()
    assert operations["logs"][0]["staff_name"] == "班主任甲"
    assert operations["logs"][0]["student_ids"] == [student_id]
    schedule_day = operations["schedule"]["days"][0]
    report_saved = client.patch(path + f"/schedule/{schedule_day['id']}", json={
        "day_type": schedule_day["day_type"], "title": schedule_day["title"], "notes": "",
        "report": {"instructor_ids": [staff["id"]], "student_ids": [student_id],
                   "lesson_content": "仅教学与管理可见的日报正文"}, "version": schedule_day["version"],
    })
    assert report_saved.status_code == 200, report_saved.text
    updated = client.patch(path + f"/daily-logs/{result.json()['id']}", json={
        "log_date": "2026-10-03", "staff_id": staff["id"], "log_type": "异常事件",
        "summary": "学员设备临时故障，已更换备用设备。", "student_ids": [student_id],
        "follow_up": "检查原设备电源。", "version": operations["logs"][0]["version"],
    })
    assert updated.status_code == 200, updated.text
    filtered = client.get(path + "/operations", params={"log_type": "异常事件"}).json()
    assert len(filtered["logs"]) == 1
    assert filtered["logs"][0]["summary"].startswith("学员设备")
    assert client.get(path + "/operations", params={"log_type": "不存在"}).status_code == 422
    assert db.scalar(select(func.count(EducationDailyLog.id))) == 1

    actor[0] = users["finance"]
    finance_view = client.get(path + "/operations")
    assert finance_view.status_code == 200
    assert finance_view.json()["can_view_logs"] is False
    assert finance_view.json()["logs"] == []
    assert finance_view.json()["schedule"]["days"][0]["report"]["lesson_content"] == ""
    assert client.post(path + "/daily-logs", json={**payload, "request_id": str(uuid4())}).status_code == 403

    actor[0] = users["other"]
    assert client.get(path + "/operations").status_code == 404


def test_education_arrears_sync_to_finance_once(setup):
    client, db, users, actor = setup
    cohort_id = _cohort(client)
    student_id = _student(client, cohort_id)
    entity_id = client.get(f"/v1/pm/education/cohorts/{cohort_id}").json()["entity_id"]
    actor[0] = users["finance"]
    payload = _receivables_payables_payload(db, entity_id)
    education_items = [item for item in payload["receivable"]["items"] if item["source"] == "education"]
    assert len(education_items) == 1
    assert education_items[0]["id"] == student_id
    assert education_items[0]["outstanding_amount"] == 1000.25
    assert education_items[0]["project_name"] == "十月托管教培"


def test_cost_and_log_validation(setup):
    client, _, _, _ = setup
    cohort_id = _cohort(client)
    path = f"/v1/pm/education/cohorts/{cohort_id}"
    invalid_cost = {
        "request_id": str(uuid4()), "occurred_on": "2026-10-01", "category": "学费",
        "detail": "课程学费", "unit_price": "100",
    }
    assert client.post(path + "/cost-documents", json=invalid_cost).status_code == 422
    invalid_period = {**invalid_cost, "request_id": str(uuid4()), "category": "饭费", "detail": "餐费套餐",
                      "occurred_on": "2026-10-10", "ended_on": "2026-10-09"}
    assert client.post(path + "/cost-documents", json=invalid_period).status_code == 422
    assert client.post(path + "/daily-logs", json={
        "request_id": str(uuid4()), "log_date": "2026-09-01", "staff_id": str(uuid4()),
        "log_type": "教学记录", "summary": "日期越界",
    }).status_code == 422


def test_cost_correction_recalculates_total_without_cross_cohort_allocation(setup):
    client, db, _, _ = setup
    first_id = _cohort(client)
    second = client.post("/v1/pm/education/cohorts", json=cohort_payload(
        name="十一月托管教培", start_date="2026-11-01",
    ))
    assert second.status_code == 200
    second_id = second.json()["id"]
    request_id = str(uuid4())
    payload = {
        "request_id": request_id, "occurred_on": "2026-10-20", "ended_on": "2026-10-21",
        "category": "活动经费", "detail": "活动物料", "unit_price": "50.00", "vendor": "物料商",
    }
    first_path = f"/v1/pm/education/cohorts/{first_id}"
    created = client.post(first_path + "/cost-documents", json=payload)
    assert created.status_code == 200, created.text
    detail_path = first_path + f"/cost-documents/{created.json()['id']}"
    detail = client.get(detail_path)
    assert detail.status_code == 200
    assert detail.json()["ledger_mode"] == "direct"
    assert detail.json()["quantity_days"] == 2
    assert len(detail.json()["allocations"]) == 1
    assert client.get(first_path).json()["expense"] == "100.00"
    assert client.get(f"/v1/pm/education/cohorts/{second_id}").json()["expense"] == "0.00"

    correction = {key: value for key, value in payload.items() if key != "request_id"}
    correction.update(version=1, unit_price="60.00")
    assert client.patch(detail_path, json=correction).status_code == 200
    assert client.patch(detail_path, json=correction).status_code == 409
    assert client.get(first_path).json()["expense"] == "120.00"
    assert client.get(f"/v1/pm/education/cohorts/{second_id}").json()["expense"] == "0.00"
    assert db.scalar(select(func.sum(EducationCostAllocation.amount))) == 120
