import React from "react";
import { createRoot } from "react-dom/client";
import { AccountRoleFields, EducationWorkspace } from "../app/education-workspace";

// Headless local UI fixture only; no network or production accounts.
const cohort = { id: "cohort-1", name: "2026年10月托管教培班", start_date: "2026-10-01", end_date: "2026-10-31",
  student_count: 12, unit_price: "3500.50", notes: "按月托管，持续招生", version: 1, owner_name: "测试教培员工",
  expected_income: "42006.00", income: "10000.00", expense: "1500.00", net: "8500.00" };
const entries = [{ id: "income-1", direction: "income", amount: "10000.00", occurred_on: "2026-10-01", purpose: "首批学费", version: 1 },
  { id: "expense-1", direction: "expense", amount: "1500.00", occurred_on: "2026-10-02", purpose: "住宿费", version: 1 }];
const students: any[] = [];
let cohortDeleted = false;
const assessments: any[] = [];
const staff = [{ id: "teacher-1", name: "测试教练", role: "助教", active: true }];
const catalog = { games: ["王者荣耀", "英雄联盟", "三角洲行动", "无畏契约", "CS2"], periods: { "8_days": "八天七晚", "1_month": "一个月", "3_months": "三个月" }, rooms: ["一人间", "两人间"], staff_roles: ["助教"], fee_details: { "学费": ["课程学费"], "活动经费": ["团建活动", "其他"], "人员成本": ["助教"], "其他": ["其他"] } };
const api = async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
  const body = options.body ? JSON.parse(String(options.body)) : {};
  if (path === "v1/pm/founder-delete-password/status") return { configured: false } as T;
  if (path === "v1/pm/founder-delete-password") return { configured: true } as T;
  if (path.endsWith("/founder-delete")) { cohortDeleted = true; return { status: "deleted" } as T; }
  if (path.endsWith("/options")) return catalog as T;
  if (path.includes("/staff/") && options.method === "DELETE") { staff[0].active = false; return { id: staff[0].id, active: false } as T; }
  if (path.endsWith("/staff")) return { items: staff } as T;
  if (path.endsWith("/operations")) return { schedule: { generated: false, days: [], monthly_summaries: [], summary: { teaching: 0, practice: 0, rest: 0 } }, costs: { items: [], ledger_total: "0.00" }, logs: [], missing_log_days: [], can_view_logs: false, can_edit: true } as T;
  if (path.endsWith("/graduation-report")) return { title: "测试学员结营报告", text: assessments.map((item) => `${item.stage_name}\n${item.observations}\n${item.final_summary || ""}\n${item.conservative_outlook || ""}\n${item.optimistic_outlook || ""}`).join("\n\n") + "\n未来预期不构成保证。" } as T;
  if (path.includes("/assessments")) {
    if (options.method === "POST") assessments.push({ ...body, id: body.request_id, version: 1, evaluator_name: "测试教练" });
    if (options.method === "PATCH") Object.assign(assessments.find((item) => item.id === path.split("/").at(-1)), body);
    return { items: [...assessments], stages: { baseline: "入学基线", phase: "阶段观察", final: "结营评估" }, dimensions: ["操作基础", "游戏理解", "团队协作", "学习执行", "生活自律"] } as T;
  }
  if (path.includes("/students")) {
    if (options.method === "POST") {
      const due = body.fees.reduce((sum: number, fee: any) => sum + Number(fee.receivable), 0);
      const cost = body.fees.reduce((sum: number, fee: any) => sum + Number(fee.cost), 0);
      students.push({ ...body, id: body.request_id, version: 1, identity_masked: "110***********1234", phone_masked: "138****5678", study_end: "2026-10-31", receivable: String(due), cost: String(cost), arrears: String(Math.max(0, due - Number(body.received))), overpayment: "0" });
      return { id: body.request_id } as T;
    }
    if (!path.endsWith("/students")) return structuredClone(students.find((item) => item.id === path.split("/").at(-1))) as T;
    const total = (field: string) => students.reduce((sum, item) => sum + Number(item[field]), 0).toFixed(2);
    return structuredClone({ items: students, has_more: false, summary: { count: students.length, receivable: total("receivable"), received: total("received"), cost: total("cost"), arrears: total("arrears") } }) as T;
  }
  if (options.method === "POST" && path.endsWith("/entries")) {
    const body = JSON.parse(String(options.body));
    entries.push({ ...body, id: body.request_id, version: 1 });
  } else if (options.method === "PATCH" && path.includes("/entries/")) {
    const entry = entries.find((item) => item.id === path.split("/").at(-1))!;
    Object.assign(entry, JSON.parse(String(options.body)), { version: entry.version + 1 });
  } else if (options.method === "PATCH") {
    Object.assign(cohort, JSON.parse(String(options.body)), { version: cohort.version + 1 });
  }
  cohort.expected_income = (cohort.student_count * Number(cohort.unit_price)).toFixed(2);
  cohort.income = entries.filter((item) => item.direction === "income").reduce((sum, item) => sum + Number(item.amount), 0).toFixed(2);
  cohort.expense = entries.filter((item) => item.direction === "expense").reduce((sum, item) => sum + Number(item.amount), 0).toFixed(2);
  cohort.net = (Number(cohort.income) - Number(cohort.expense)).toFixed(2);
  if (options.method) return { id: cohort.id } as T;
  if (path === "v1/pm/education/cohorts") return structuredClone({ items: cohortDeleted ? [] : [cohort], summary: { ...cohort, cohort_count: cohortDeleted ? 0 : 1, student_cost: "0.00", cost: "0.00", cash_expense: cohort.expense, operating_expense: cohort.expense }, has_more: false, can_edit: true, can_delete: new URLSearchParams(location.search).has("founder"), scope: "mine" }) as T;
  return structuredClone({ ...cohort, entries }) as T;
};
createRoot(document.getElementById("root")!).render(<>
  <style>{`body{font-family:Arial,"Microsoft YaHei",sans-serif;background:#f3f5f8;margin:0;padding:24px;color:#203347}*{box-sizing:border-box}.panel{padding:24px;background:white;border:1px solid #e0e6ec;border-radius:16px}button{cursor:pointer}.primaryButton{padding:12px;background:#e51932;border:0;border-radius:8px;color:white}.secondaryButton{padding:12px;border:1px solid #cde0ee;border-radius:8px;background:#fff}.noticeBar{padding:14px;background:#e4f5ed}.roleFixture{margin-bottom:20px;padding:12px;display:flex;gap:20px}`}</style>
  <form className="roleFixture"><AccountRoleFields initialRole="business" initialCeiling="L4" /></form>
  <EducationWorkspace api={api} token="local-test-only" initialModule="cohorts" />
</>);
