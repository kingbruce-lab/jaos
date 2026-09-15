import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const page = fs.readFileSync("app/page.tsx", "utf8");
const education = fs.readFileSync("app/education-workspace.tsx", "utf8");
const ledger = fs.readFileSync("app/education-ledger.tsx", "utf8");
const operations = fs.readFileSync("app/education-operations.tsx", "utf8");

test("education has its own project module and account role without generic PM fetch", () => {
  assert.match(page, /<EducationWorkspace[^>]*api=\{kbFetch\}/);
  assert.match(page, /user\?\.organization_role === "education"\s*\n\s*\|\| \(\["education", "education-ledger"\]\.includes\(projectModule\)/);
  assert.match(education, /<option value="education">教培<\/option>/);
  assert.match(education, /role === "education" \? "L1" : ceiling/);
});

test("education starts the cross-cohort ledger and uses confirmed course durations", () => {
  assert.match(page, /教培综合台账/);
  assert.match(page, /education-ledger/);
  assert.match(page, /星曜教培 · 班期管理/);
  assert.match(education, /综合台账/);
  assert.match(education, /一个月29天、三个月87天/);
  assert.match(ledger, /学费是一口价套餐，已包含住宿与餐饮/);
  assert.match(ledger, /分期与收退款/);
  assert.match(ledger, /payment-ledger/);
});

test("education separates expected and actual income and protects repeated writes", () => {
  assert.match(education, /预计收入/);
  assert.match(education, /总收入/);
  assert.match(education, /总成本/);
  assert.match(education, /逐项登记收入 \/ 费用支出/);
  assert.match(education, /保存本项并继续添加/);
  assert.match(education, /实时结余/);
  assert.match(education, /educationStickyMetrics/);
  assert.match(education, /request_id = createId.current/);
  assert.match(education, /request_id = entryId.current/);
  assert.match(education, /body.version = editing.version/);
  assert.match(education, /body.version = detail.version/);
});

test("education phase two provides 6+1 calendar, direct daily-price costs, daily logs and finance sync", () => {
  assert.match(education, /EducationOperations/);
  assert.match(operations, /6＋1 教学日历/);
  assert.match(operations, /单价（元\/天）/);
  assert.match(operations, /自动总价/);
  assert.match(operations, /总价＝每日单价 × 天数/);
  assert.match(operations, /已直接计入班期总账/);
  assert.doesNotMatch(operations, /分摊方式/);
  assert.doesNotMatch(operations, /allocation_mode/);
  assert.match(operations, /点击填写日报/);
  assert.match(operations, /课程目标/);
  assert.match(operations, /学员表现与进步/);
  assert.match(operations, /周日/);
  assert.match(operations, /每29天为一个教学月/);
  assert.match(operations, /teaching-month-summaries/);
  assert.match(operations, /educationReportOverlay/);
  assert.match(operations, /toggleDayFlag/);
  assert.match(operations, /特殊成绩日/);
  assert.match(operations, /出现问题日/);
  assert.match(operations, /name="attachments"/);
  assert.doesNotMatch(operations, /name="allocation_month"/);
  assert.match(operations, /补充记录与异常事项（可选）/);
  assert.match(operations, /这里只用于同一天由不同老师追加/);
  assert.match(operations, /name="ended_on"/);
  assert.match(operations, /逐项登记费用支出/);
  assert.match(education, /name="ended_on"/);
  assert.match(page, /星曜教培同步/);
});

test("education combines referral, commission and every assigned teacher in the student record", () => {
  const enrollment = fs.readFileSync("app/education-enrollment.tsx", "utf8");
  const catalog = fs.readFileSync("agent/app/education_catalog.py", "utf8");
  const backend = fs.readFileSync("agent/app/education_enrollment.py", "utf8");
  assert.match(enrollment, /推荐人/);
  assert.match(enrollment, /推荐渠道/);
  assert.match(enrollment, /本学员课程周期与全部师资/);
  assert.match(enrollment, /添加并继续下一位/);
  assert.match(catalog, /状态恢复师/);
  assert.match(catalog, /推荐渠道提成费/);
  assert.match(backend, /其他教师请在人员备注中注明/);
  assert.match(backend, /同一学员不能重复添加同一位人员/);
});
