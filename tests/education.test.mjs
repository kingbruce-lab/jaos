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
  assert.match(education, /累计实际收入/);
  assert.match(education, /累计实际支出/);
  assert.match(education, /累计收支结余/);
  assert.match(education, /request_id = createId.current/);
  assert.match(education, /request_id = entryId.current/);
  assert.match(education, /body.version = editing.version/);
  assert.match(education, /body.version = detail.version/);
});

test("education phase two provides 6+1 calendar, source costs, daily logs and finance sync", () => {
  assert.match(education, /EducationOperations/);
  assert.match(operations, /6＋1 教学日历/);
  assert.match(operations, /原始成本只记一次/);
  assert.match(operations, /均摊至本期在册学员/);
  assert.match(operations, /点击填写完整日报/);
  assert.match(operations, /课程目标/);
  assert.match(operations, /学员表现与进步/);
  assert.match(operations, /补充记录与异常事项（可选）/);
  assert.match(operations, /这里只用于同一天由不同老师追加/);
  assert.match(operations, /name="ended_on"/);
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
