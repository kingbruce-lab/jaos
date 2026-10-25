import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build, preview } from "vite";
import react from "@vitejs/plugin-react";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "jaos-finance-ui-"));
const screenshots = path.join(os.tmpdir(), "jaos-finance-ui-screenshots");
fs.mkdirSync(screenshots, { recursive: true });
await build({ configFile: false, plugins: [react()], build: { outDir, rollupOptions: { input: "tests/finance-ui.html" } } });
const server = await preview({ configFile: false, build: { outDir }, preview: { host: "127.0.0.1", port: 4183, strictPort: true } });
const browser = await chromium.launch({ executablePath: process.env.JAOS_BROWSER_EXECUTABLE || (fs.existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : chromium.executablePath()), headless: true, args: ["--no-sandbox"] });
const errors = [];
const baseUrl = "http://127.0.0.1:4183/tests/finance-ui.html";
const tabs = ["资金总览", "银行流水", "应收应付", "用途复核", "年度分析", "编码账簿", "账外现金"];
const retiredPanelsAbsent = async (page) => {
  for (const name of ["资金健康", "集团内部划转", "上周收入前 10 公司 / 单位", "上周支出前 10 公司 / 单位", "上周风险与异常预警"]) {
    assert.equal(await page.getByRole("heading", { name, exact: true, includeHidden: true }).count(), 0, `Retired panel must not return: ${name}`);
  }
  assert.equal(await page.locator(".financeHealthSection, .financeInternalTransferPanel, .financeWeeklyInsights").count(), 0, "Removed finance panels must not be mounted, including hidden navigation content");
  assert.equal(await page.getByRole("tablist", { name: "财务功能", exact: true }).getByRole("tab", { name: /^内部划转/ }).count(), 0, "The retired transfer-management tab must remain removed");
};
const tab = (page, name) => page.getByRole("tablist", { name: "财务功能", exact: true }).getByRole("tab", { name: new RegExp(`^${name}`) });
const navigate = async (page, name, touch = false) => { const target = tab(page, name); await target.scrollIntoViewIfNeeded(); if (touch) await target.tap(); else await target.click(); await target.waitFor(); await retiredPanelsAbsent(page); };
const frames = async (page) => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const top = async (page) => { await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" })); await frames(page); };
const noOverflow = async (page, name) => {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `${name}: page must fit the viewport`);
  assert.equal(await page.locator(".financeWorkspaceV2").evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, `${name}: finance workspace must fit the space remaining after navigation`);
};
const readableMoney = async (page, description) => {
  for (const amount of await page.locator(".financeHeroCopy > strong, .financeMetricGrid strong, .financeAnnualMetricGrid strong, .financeCostCenterMetrics strong, .financeAnnualCategoryPanel b, .financeObligationsTotals strong, .cashEntryList b").all()) {
    if (!await amount.isVisible()) continue;
    assert.equal(await amount.evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, `${description}: currency values must be fully readable`);
  }
};
const stickyNavigation = async (page, description) => {
  await top(page);
  const naturalTop = await page.locator(".financePrimaryNav").evaluate((element) => element.getBoundingClientRect().top);
  await page.evaluate((position) => window.scrollTo({ top: position + 220, behavior: "instant" }), naturalTop);
  await frames(page);
  const geometry = await page.locator(".financePrimaryNav").evaluate((element) => {
    const rect = element.getBoundingClientRect(), style = getComputedStyle(element);
    return { top: rect.top, expected: Number.parseFloat(style.top), position: style.position, scrollY };
  });
  assert.ok(geometry.scrollY >= 200, `${description}: measure sticky after real deep page scrolling`);
  assert.equal(geometry.position, "sticky");
  assert.ok(Math.abs(geometry.top - geometry.expected) <= 1.5, `${description}: navigation must remain at the safe-area top: ${JSON.stringify(geometry)}`);
};
const touchTarget = async (target, description) => {
  const box = await target.boundingBox();
  assert.ok(box && box.width >= 43.5 && box.height >= 43.5, `${description} must offer a 44px touch target: ${JSON.stringify(box)}`);
};
const visibleFields = async (page) => {
  for (const field of await page.locator('.financeWorkspaceV2 input:not([type=hidden]):not([type=checkbox]):not([type=file]), .financeWorkspaceV2 select, .financeWorkspaceV2 textarea').all()) {
    if (!await field.isVisible()) continue;
    const font = await field.evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize));
    assert.ok(font >= 16, `Mobile input text should not trigger iOS focus zoom: ${font}px`);
    await touchTarget(field, await field.getAttribute("name") || "finance field");
  }
};
const action = async (page, expected) => page.waitForFunction((value) => document.querySelector('[data-testid="last-action"]')?.textContent === value, expected);
const payload = async (page) => JSON.parse(await page.getByTestId("last-payload").textContent());

async function prepare(page) {
  page.on("pageerror", (error) => errors.push(error.message));
  let failedCodes = false;
  await page.route("**/api/kb/**", async (route) => {
    const url = new URL(route.request().url());
    const data = await page.evaluate(() => window.financeFixtureReads);
    await page.evaluate((scope) => { document.documentElement.dataset.financeApiScope = scope; }, url.search);
    const base = { confidentiality: "L4", entity_id: url.searchParams.get("entity_id"), entity_name: data.companyName, confirmed_only: true, include_internal_transfers: url.searchParams.get("include_internal_transfers") === "true" };
    if (url.pathname.endsWith("/finance/cost-centers")) {
      const shouldFail = new URL(page.url()).searchParams.has("fail_codes");
      if (shouldFail && !failedCodes) { failedCodes = true; await route.fulfill({ status: 503, json: { detail: "本地测试：编码账簿暂时不可用" } }); return; }
      await route.fulfill({ json: { ...base, items: data.costCenters } }); return;
    }
    if (/\/finance\/cost-centers\/[^/]+\/transactions$/.test(url.pathname)) {
      const code = decodeURIComponent(url.pathname.split("/").at(-2));
      const center = data.costCenters.find((item) => item.code === code);
      await route.fulfill({ json: { ...base, code, label: center?.label || code, income: center?.income || "0", expense: center?.expense || "0", net: center?.net || "0", transaction_count: 1, items: data.ledgerItems.map((item) => ({ ...item, project_reference: code, income: center?.income || "0" })) } }); return;
    }
    if (url.pathname.endsWith("/finance/annual-transactions/search")) {
      const query = url.searchParams.get("q") || "";
      if (query === "延迟") await new Promise((resolve) => setTimeout(resolve, 650));
      await route.fulfill({ json: { ...base, year: Number(url.searchParams.get("year")), query, total: query === "无结果" ? 0 : 1, limit: 100, items: query === "无结果" ? [] : data.ledgerItems.map((item) => ({ ...item, matched_fields: ["往来单位", "实际用途"] })) } }); return;
    }
    await route.fulfill({ status: 404, json: { detail: `Unexpected fixture request: ${url.pathname}` } });
  });
}

async function importForm(page) {
  const form = page.locator(".financeOperationCard").filter({ hasText: "导入银行流水" }).locator("form");
  if (!await form.isVisible()) {
    const importer = page.getByRole("button", { name: /导入银行流水|上传流水/ }).first();
    if (await importer.count()) await importer.click();
    else await page.locator("details").filter({ has: form }).locator(":scope > summary").click();
  }
  await form.waitFor();
  return form;
}

async function openBatch(page, filename = "2026年10月公司银行流水_已核对.xlsx", touch = false) {
  await navigate(page, "银行流水", touch);
  const button = page.getByRole("button", { name: `查看流水 ${filename}`, exact: true });
  await button.scrollIntoViewIfNeeded();
  if (touch) await button.tap(); else await button.click();
  await page.getByRole("button", { name: "返回银行流水", exact: true }).waitFor();
}

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  await prepare(page);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await tab(page, "资金总览").waitFor();
  await noOverflow(page, "desktop overview");
  assert.match(await page.locator(".financeHeroCopy").innerText(), /1,234,567,890\.99/);
  const originalBalance = await page.getByTestId("bank-balance").textContent();
  await retiredPanelsAbsent(page);
  await page.getByRole("button", { name: "当前：剔除内部划转", exact: true }).click();
  assert.equal(await page.getByTestId("scope").textContent(), "including");
  assert.equal(await page.getByTestId("bank-balance").textContent(), originalBalance, "Including internal transfers must never change bank balances");
  await top(page); await page.screenshot({ path: path.join(screenshots, "overview-desktop.png"), fullPage: true });
  await top(page); await page.screenshot({ path: path.join(screenshots, "overview-desktop-viewport.png") });

  await navigate(page, "应收应付");
  await page.locator(".financeObligationCreate > summary").click();
  const obligationForm = page.locator(".financeObligationCreate form");
  await obligationForm.locator('[name=due_date]').fill("2026-11-30");
  await obligationForm.locator('[name=amount]').fill("300000.25");
  await obligationForm.locator('[name=actual_amount]').fill("50000");
  await obligationForm.locator('[name=counterparty]').fill("本地财务补充客户");
  await obligationForm.locator('[name=note]').fill("待收取的活动服务尾款");
  await obligationForm.getByRole("button").click();
  await action(page, "receivable-payable-create");
  assert.equal((await payload(page)).amount, "300000.25");
  await page.locator(".financeObligationItem").filter({ hasText: "本地财务补充客户" }).waitFor();
  await page.screenshot({ path: path.join(screenshots, "obligations-desktop.png"), fullPage: true });

  await navigate(page, "银行流水");
  const uploadForm = await importForm(page);
  await uploadForm.locator('[name=account_number]').fill("1234567890123456");
  await uploadForm.locator('[name=file]').setInputFiles({ name: "本地验证流水.csv", mimeType: "text/csv", buffer: Buffer.from("日期,收入,支出,余额\n2026-10-24,100,0,100\n") });
  await uploadForm.getByRole("button", { name: "上传并解析流水", exact: true }).click();
  await action(page, "upload");
  await page.getByRole("button", { name: "返回银行流水", exact: true }).waitFor();
  assert.match(await page.locator(".financeBatchDetailHeader").innerText(), /本地验证流水\.csv|待财务核对/);
  await page.getByRole("button", { name: "返回银行流水", exact: true }).click();
  await page.getByRole("button", { name: "查看流水 本地验证流水.csv", exact: true }).waitFor();
  assert.equal((await payload(page)).entity_id, "entity-jingao");

  await openBatch(page, "2026年10月补充流水_待确认.csv");
  await page.getByRole("button", { name: "核对 / 用途修正", exact: true }).click();
  const pendingEditor = page.locator(".transactionEditExpanded:visible");
  await pendingEditor.locator('[name=counterparty]').fill("已核验的赛事合作客户");
  await pendingEditor.locator('[name=category]').fill("赛事服务");
  await pendingEditor.locator('[name=project_reference]').selectOption("CC26B10");
  await pendingEditor.getByRole("button", { name: "保存分类与项目", exact: true }).click();
  await action(page, "transaction-transaction-pending");
  assert.equal((await payload(page)).annotation_only, "false");
  assert.equal((await payload(page)).counterparty, "已核验的赛事合作客户");
  await page.getByRole("button", { name: "返回银行流水", exact: true }).click();
  const pendingBatch = page.locator(".financeBatchList article").filter({ hasText: "2026年10月补充流水_待确认.csv" });
  await pendingBatch.getByRole("button", { name: "确认流水", exact: true }).click();
  await action(page, "confirm-batch-pending");
  assert.match(await pendingBatch.innerText(), /财务已确认/);
  assert.equal(await pendingBatch.getByRole("button", { name: "删除已确认批次", exact: true }).count(), 0, "Finance users cannot delete a confirmed batch");

  await openBatch(page);
  await page.getByRole("button", { name: "分类 / 用途修正", exact: true }).first().click();
  const confirmedEditor = page.locator(".transactionEditExpanded:visible");
  assert.equal(await confirmedEditor.locator('[name=counterparty]').count(), 0, "A confirmed transaction cannot edit bank identity");
  assert.equal(await confirmedEditor.locator('[name=transacted_at]').count(), 0, "A confirmed transaction cannot edit its bank timestamp");
  await confirmedEditor.locator('[name=category]').fill("已核验培训收入");
  await confirmedEditor.getByRole("button", { name: "保存分类与项目", exact: true }).click();
  await action(page, "transaction-transaction-1");
  const classificationPayload = await payload(page);
  assert.equal(classificationPayload.annotation_only, "true");
  assert.equal(Object.hasOwn(classificationPayload, "counterparty"), false);
  assert.equal(Object.hasOwn(classificationPayload, "transacted_at"), false);
  await page.getByRole("button", { name: "分类 / 用途修正", exact: true }).first().click();
  await page.locator(".purposeCorrectionForm:visible textarea").fill("新秀训练营第一阶段合同服务收入");
  await page.getByRole("button", { name: "提交创始人复核", exact: true }).click();
  await action(page, "purpose-request-transaction-1");
  assert.equal(await page.getByRole("button", { name: "批准并采用", exact: true }).count(), 0);
  await page.locator(".transactionPanel .bankRawSummary:visible").first().locator(":scope > summary").click();
  assert.match(await page.locator(".transactionPanel").innerText(), /银行原始附言：2026训练服务合同首期回款，不可覆盖/);
  assert.equal(await page.locator(".transactionPanel [name=summary]").count(), 0, "Bank source evidence must never be an editable field");
  await top(page); await page.screenshot({ path: path.join(screenshots, "transactions-desktop.png"), fullPage: true });
  await top(page); await page.screenshot({ path: path.join(screenshots, "transactions-desktop-viewport.png") });

  await navigate(page, "年度分析");
  await page.getByRole("tab", { name: "2025 年度", exact: true }).click();
  await page.getByLabel("流水检索关键字", { exact: true }).fill("腾竞");
  await page.getByRole("button", { name: "检索年度流水", exact: true }).click();
  await page.getByText("找到 1 条流水", { exact: true }).waitFor();
  const searchScope = new URLSearchParams(await page.locator("html").getAttribute("data-finance-api-scope"));
  assert.equal(searchScope.get("year"), "2025");
  assert.equal(searchScope.get("entity_id"), "entity-jingao");
  assert.equal(searchScope.get("include_internal_transfers"), "true");
  await noOverflow(page, "annual analysis");
  await top(page); await page.screenshot({ path: path.join(screenshots, "annual-desktop.png"), fullPage: true });
  await top(page); await page.screenshot({ path: path.join(screenshots, "annual-desktop-viewport.png") });
  await page.getByLabel("流水检索关键字", { exact: true }).fill("延迟");
  const pendingSearch = page.waitForRequest((request) => request.url().includes("annual-transactions/search") && new URL(request.url()).searchParams.get("q") === "延迟");
  await page.getByRole("button", { name: "检索年度流水", exact: true }).click();
  await pendingSearch;
  await page.getByRole("tab", { name: "2026 年度", exact: true }).click();
  await page.waitForTimeout(900);
  assert.equal(await page.locator(".financeAnnualSearchResults").count(), 0, "A late annual search response must not appear under the newly selected year");
  await page.getByLabel("流水检索关键字", { exact: true }).fill("腾竞");
  await page.getByRole("button", { name: "检索年度流水", exact: true }).click();
  await page.getByText("找到 1 条流水", { exact: true }).waitFor();
  await page.locator(".financeAnnualSearchResults").getByRole("button", { name: "查看所在批次", exact: true }).click();
  await page.getByRole("button", { name: "返回银行流水", exact: true }).waitFor();

  await navigate(page, "编码账簿");
  await page.getByLabel("搜索公司编码", { exact: true }).fill("KPL");
  await page.getByRole("button", { name: /CC26B10.*KPL/ }).click();
  await page.getByLabel("切换公司编码", { exact: true }).waitFor();
  await page.locator(".financeCostCenterMetrics").filter({ hasText: "1,200,000.25" }).waitFor();
  assert.match(await page.locator(".financeCostCenterLedgerPanel").innerText(), /1,200,000\.25/);
  await noOverflow(page, "cost center detail");
  await top(page); await page.screenshot({ path: path.join(screenshots, "cost-center-desktop.png"), fullPage: true });
  await page.getByRole("button", { name: /返回编码目录/ }).click();
  assert.equal(await page.getByLabel("搜索公司编码", { exact: true }).inputValue(), "KPL");

  await navigate(page, "账外现金");
  const cashForm = page.locator(".financeCashStandaloneGrid .businessForm");
  await cashForm.getByLabel("金额", { exact: true }).fill("2300.25");
  await cashForm.getByLabel("说明", { exact: true }).fill("本地现金差旅报销，与银行账户分离");
  await cashForm.getByRole("button", { name: "登记现金记录", exact: true }).click();
  await action(page, "cash");
  assert.match(await page.locator(".cashEntryList").innerText(), /2,300\.25/);
  assert.equal(await page.getByTestId("bank-balance").textContent(), originalBalance, "Off-book cash entry must not change the bank account balance");

  await page.getByRole("tablist", { name: "公司财务账套", exact: true }).getByRole("tab", { name: /王牌猎豹/ }).click();
  assert.equal(await page.getByRole("tablist", { name: "公司财务账套", exact: true }).getByRole("tab", { name: /王牌猎豹/ }).getAttribute("aria-selected"), "true");
  assert.equal(await page.getByTestId("bank-balance").textContent(), "88888.88");
  assert.match(await page.locator(".financePageHeader").innerText(), /王牌猎豹/);
  assert.equal(await tab(page, "账外现金").count(), 0, "Only the headquarters exposes the off-book cash ledger");
  assert.equal(await tab(page, "编码账簿").count(), 0, "Other entities do not inherit headquarters cost-center menus");

  console.log("Finance desktop workflows: bank originals, permissions, annual race and ledgers passed; checking failure recovery");
  await page.goto(`${baseUrl}?loading=1`, { waitUntil: "domcontentloaded" });
  await page.locator(".financeLoadingState").waitFor();
  assert.equal(await page.locator(".financeHeroCopy > strong:visible").count(), 0, "A company/scope refresh must not temporarily show zero or stale balances");
  await noOverflow(page, "financial loading state");

  await page.goto(`${baseUrl}?long_list=1`, { waitUntil: "domcontentloaded" });
  await navigate(page, "银行流水");
  await page.getByLabel("搜索银行批次", { exact: true }).fill("历史银行流水");
  await page.getByLabel("筛选批次确认状态", { exact: true }).selectOption("confirmed");
  assert.equal(await page.getByRole("button", { name: /^查看流水 历史银行流水/ }).count(), 12);
  const lastBatch = page.getByRole("button", { name: "查看流水 历史银行流水12.xlsx", exact: true });
  await lastBatch.scrollIntoViewIfNeeded();
  const bankListY = await page.evaluate(() => window.scrollY);
  assert.ok(bankListY > 200, "Use a deep batch list to verify return position");
  await lastBatch.click();
  await page.getByRole("button", { name: "返回银行流水", exact: true }).click();
  await page.waitForFunction((position) => Math.abs(scrollY - position) < 100, bankListY);
  assert.equal(await page.getByLabel("搜索银行批次", { exact: true }).inputValue(), "历史银行流水");
  assert.equal(await page.getByLabel("筛选批次确认状态", { exact: true }).inputValue(), "confirmed");

  await page.goto(`${baseUrl}?fail_save=1`, { waitUntil: "domcontentloaded" });
  await openBatch(page);
  await page.getByRole("button", { name: "分类 / 用途修正", exact: true }).first().click();
  await page.locator(".transactionEditExpanded:visible [name=category]").fill("保留中的财务分类");
  await page.locator(".transactionEditExpanded:visible").getByRole("button", { name: "保存分类与项目", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "分类保存失败" }).waitFor();
  assert.equal(await page.locator(".transactionEditExpanded:visible [name=category]").inputValue(), "保留中的财务分类");
  await page.locator(".transactionEditExpanded:visible").getByRole("button", { name: "保存分类与项目", exact: true }).click();
  await action(page, "transaction-transaction-1");

  await page.goto(`${baseUrl}?fail_upload=1`, { waitUntil: "domcontentloaded" });
  await navigate(page, "银行流水");
  const failedUpload = await importForm(page);
  await failedUpload.locator('[name=account_number]').fill("1234567890123456");
  await failedUpload.locator('[name=file]').setInputFiles({ name: "失败后重试.csv", mimeType: "text/csv", buffer: Buffer.from("日期,收入,支出,余额\n2026-10-24,100,0,100\n") });
  await failedUpload.getByRole("button", { name: "上传并解析流水", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "暂时无法导入" }).waitFor();
  assert.equal(await failedUpload.isVisible(), true);
  assert.equal(await page.getByRole("button", { name: "返回银行流水", exact: true }).count(), 0, "Failed imports must keep the form instead of opening stale transaction details");
  await failedUpload.getByRole("button", { name: "上传并解析流水", exact: true }).click();
  await page.getByRole("button", { name: "返回银行流水", exact: true }).waitFor();

  await page.goto(`${baseUrl}?role=viewer`, { waitUntil: "domcontentloaded" });
  await navigate(page, "银行流水");
  assert.equal(await page.getByRole("button", { name: "上传并解析流水", exact: true }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "确认流水", exact: true }).count(), 0);
  assert.equal(await page.getByRole("button", { name: /删除.*批次/ }).count(), 0);
  await openBatch(page);
  assert.equal(await page.getByRole("button", { name: "分类 / 用途修正", exact: true }).count(), 0);
  await navigate(page, "应收应付");
  assert.equal(await page.locator(".financeObligationCreate").count(), 0);
  await navigate(page, "用途复核");
  assert.equal(await page.getByRole("button", { name: "批准并采用", exact: true }).count(), 0);

  await page.goto(`${baseUrl}?role=founder`, { waitUntil: "domcontentloaded" });
  await navigate(page, "用途复核");
  await page.getByRole("button", { name: "批准并采用", exact: true }).click();
  await action(page, "purpose-review-correction-1");
  assert.equal(await page.getByRole("button", { name: "批准并采用", exact: true }).count(), 0);
  await navigate(page, "银行流水");
  assert.equal(await page.getByRole("button", { name: "删除已确认批次", exact: true }).count(), 1);
  assert.equal(await page.getByRole("button", { name: "确认流水", exact: true }).count(), 0, "Founder review rights do not grant finance upload/confirmation rights");

  for (const [width, height] of [[320, 740], [360, 800], [390, 844], [430, 932], [667, 375], [844, 390]]) {
    console.log(`Finance touch viewport ${width}x${height}`);
    const context = await browser.newContext({ viewport: { width, height }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
    const mobile = await context.newPage();
    await prepare(mobile);
    await mobile.goto(`${baseUrl}?shell=1`, { waitUntil: "domcontentloaded" });
    await tab(mobile, "资金总览").waitFor();
    await retiredPanelsAbsent(mobile);
    await noOverflow(mobile, `mobile ${width} overview`);
    if (width === 390 || width === 667) await stickyNavigation(mobile, `${width}px overview`);
    await top(mobile); await mobile.screenshot({ path: path.join(screenshots, `overview-${width}x${height}-viewport.png`) });
    for (const name of tabs) {
      await navigate(mobile, name, true);
      await noOverflow(mobile, `mobile ${width} ${name}`);
      await visibleFields(mobile);
      await readableMoney(mobile, `${width}px ${name}`);
      await touchTarget(tab(mobile, name), `Finance navigation ${name}`);
      if (name === "银行流水") {
        await openBatch(mobile, undefined, true);
        await noOverflow(mobile, `mobile ${width} bank detail`);
        const edit = mobile.getByRole("button", { name: "分类 / 用途修正", exact: true }).first();
        await edit.scrollIntoViewIfNeeded(); await edit.tap();
        await visibleFields(mobile);
        assert.equal(await mobile.locator(".transactionEditExpanded:visible [name=counterparty]").count(), 0);
        if (width === 390 || width === 667) {
          const editor = mobile.locator(".transactionEditExpanded:visible");
          await editor.locator('[name=category]').fill("手机端已核验分类");
          await editor.getByRole("button", { name: "保存分类与项目", exact: true }).tap();
          await action(mobile, "transaction-transaction-1");
          assert.equal((await payload(mobile)).annotation_only, "true");
        }
        await top(mobile); await mobile.screenshot({ path: path.join(screenshots, `transactions-${width}x${height}-viewport.png`) });
      }
      if (name === "账外现金" && (width === 390 || width === 667)) {
        const cash = mobile.locator(".financeCashStandaloneGrid .businessForm");
        await cash.getByLabel("金额", { exact: true }).fill("1234.50");
        await cash.getByLabel("说明", { exact: true }).fill("手机端本地现金登记");
        const submit = cash.getByRole("button", { name: "登记现金记录", exact: true });
        await submit.scrollIntoViewIfNeeded(); await submit.tap();
        await action(mobile, "cash");
        assert.match(await mobile.locator(".cashEntryList").innerText(), /1,234\.50/);
      }
      if (name === "编码账簿") {
        const center = mobile.getByRole("button", { name: /CC26B10.*KPL/ });
        await center.scrollIntoViewIfNeeded(); await center.tap();
        await mobile.getByLabel("切换公司编码", { exact: true }).waitFor();
        await mobile.locator(".financeCostCenterMetrics").filter({ hasText: "1,200,000.25" }).waitFor();
        await noOverflow(mobile, `mobile ${width} cost-center detail`);
      }
      await mobile.screenshot({ path: path.join(screenshots, `${name}-${width}x${height}.png`), fullPage: true });
    }
    await context.close();
  }
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: "passed", checks: "7 finance levels, 5 retired panels remain absent, context/period/transfer scope, bank originals and permissions, loading state, filtered batch return position, upload/save recovery, late annual response isolation, pending/confirmed editing, purpose workflow, obligations, cash, cost-center detail/back, annual search/batch link, desktop and 6 touch portrait/landscape sizes, sticky deep scrolling, 44px targets and 16px inputs", screenshots }));
} finally {
  await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
  fs.rmSync(outDir, { recursive: true, force: true });
}
