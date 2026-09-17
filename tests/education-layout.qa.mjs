import assert from "node:assert/strict";
import { build, preview } from "vite";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "jaos-education-layout-"));
await build({ configFile: false, plugins: [react()], build: { outDir, rollupOptions: { input: "tests/education-ui.html" } } });
const server = await preview({ configFile: false, build: { outDir }, preview: { host: "127.0.0.1", port: 4180, strictPort: true } });
const browser = await chromium.launch({ channel: "msedge", headless: true, timeout: 30000 });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:4180/tests/education-ui.html", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /2026年10月托管教培班/ }).click();
  await page.getByRole("heading", { name: "6＋1 教学日历" }).waitFor();
  assert.equal(await page.evaluate(() => {
    const accounting = document.querySelector(".educationEntries");
    const costs = document.querySelector(".educationCostEntrySection");
    const calendar = document.querySelector(".educationCalendarSection");
    return Boolean(accounting && costs && calendar
      && (accounting.compareDocumentPosition(costs) & Node.DOCUMENT_POSITION_FOLLOWING)
      && (costs.compareDocumentPosition(calendar) & Node.DOCUMENT_POSITION_FOLLOWING));
  }), true);
  await page.locator('.educationCostEntrySection [name="category"]').selectOption("教学房间");
  assert.equal(await page.locator('.educationCostEntrySection [name="detail"]').inputValue(), "训练室");

  await page.getByLabel("金额（元）", { exact: true }).fill("2500.50");
  await page.getByLabel("收支用途", { exact: true }).fill("补缴学费");
  const saveEntry = page.getByRole("button", { name: "保存本项并继续添加", exact: true });
  await saveEntry.scrollIntoViewIfNeeded();
  const beforeEntryY = await page.evaluate(() => window.scrollY);
  assert.ok(beforeEntryY > 0);
  await saveEntry.click();
  await page.getByText("本期公共收支明细（3）").waitFor();
  assert.ok(Math.abs((await page.evaluate(() => window.scrollY)) - beforeEntryY) < 100);

  const cohortEditor = page.getByText("编辑班期、招生人数和客单价", { exact: true });
  await cohortEditor.click();
  await page.locator('.educationDetail [name="student_count"]').fill("14");
  const saveCohort = page.getByRole("button", { name: "保存班期", exact: true });
  await saveCohort.scrollIntoViewIfNeeded();
  const beforeCohortY = await page.evaluate(() => window.scrollY);
  await saveCohort.click();
  await page.waitForFunction(() => document.querySelector(".educationSecondaryMetrics")?.textContent.includes("49,007.00"));
  assert.ok(Math.abs((await page.evaluate(() => window.scrollY)) - beforeCohortY) < 100);
  assert.equal(await page.locator('.educationDetail details:has(> summary:text("编辑班期、招生人数和客单价"))').getAttribute("open"), "");
  await page.getByText("＋ 新增学员报名", { exact: true }).click();
  const enrollment = page.locator(".educationEnrollment");
  await enrollment.getByLabel("学员姓名", { exact: true }).fill("测试学员");
  const saveStudent = enrollment.getByRole("button", { name: "保存报名", exact: true });
  await saveStudent.scrollIntoViewIfNeeded();
  const beforeStudentY = await page.evaluate(() => window.scrollY);
  await saveStudent.click();
  await enrollment.locator(".educationStudentList article").filter({ hasText: "测试学员" }).waitFor();
  assert.ok(Math.abs((await page.evaluate(() => window.scrollY)) - beforeStudentY) < 100);
  assert.deepEqual(errors, []);
  console.log("Education accounting layout, category, and save position passed");
} finally {
  await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
}
