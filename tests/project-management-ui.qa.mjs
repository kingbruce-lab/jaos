import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build, preview } from "vite";
import react from "@vitejs/plugin-react";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "jaos-project-ui-"));
const screenshots = path.join(os.tmpdir(), "jaos-project-ui-screenshots");
fs.mkdirSync(screenshots, { recursive: true });
await build({ configFile: false, plugins: [react()], build: { outDir, rollupOptions: { input: "tests/project-management-ui.html" } } });
const server = await preview({ configFile: false, build: { outDir }, preview: { host: "127.0.0.1", port: 4182, strictPort: true } });
const browser = await chromium.launch({
  executablePath: process.env.JAOS_BROWSER_EXECUTABLE || (fs.existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : chromium.executablePath()),
  headless: true,
  args: ["--no-sandbox"],
});
const errors = [];
const projectName = "2026KPL冬季新秀训练营与跨区域电竞人才培养联合交付项目";
const clientName = "天竞华娱（苏州）文化传播有限公司与联合赛事运营事业部";
const openProject = async (page, name = projectName) => {
  await page.getByRole("button", { name: `查看项目 ${name}`, exact: true }).click();
  await page.getByRole("heading", { name, exact: true }).waitFor();
};
const noOverflow = async (page) => {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, "The page must not overflow horizontally");
  assert.equal(await page.locator(".pmWorkspaceV2").evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, "The workspace must fit the space left by global navigation");
};

const mobileScreenshots = path.join(os.tmpdir(), "jaos-project-mobile-screenshots");
fs.mkdirSync(mobileScreenshots, { recursive: true });
const touchTarget = async (locator, description) => {
  const box = await locator.boundingBox();
  assert.ok(box && box.width >= 43.5 && box.height >= 43.5, `${description} needs a 44px touch target: ${JSON.stringify(box)}`);
};
const tap = async (locator) => {
  await locator.evaluate((element) => element.scrollIntoView({ block: "center", inline: "nearest" }));
  await touchTarget(locator, await locator.innerText());
  await locator.tap();
};
const mobileFields = async (page) => {
  const fields = page.locator(".pmWorkspaceV2 input:not([type=checkbox]):not([type=file]), .pmWorkspaceV2 select, .pmWorkspaceV2 textarea");
  for (const field of await fields.all()) {
    if (!await field.isVisible()) continue;
    const font = await field.evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize));
    assert.ok(font >= 16, `Mobile inputs must use at least 16px text to avoid iOS focus zoom; got ${font}`);
    await touchTarget(field, await field.getAttribute("name") || "form field");
  }
};
const settleFrames = async (page) => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const checkStickyTabs = async (page, description) => {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await settleFrames(page);
  await page.locator(".pmDetailTabs").evaluate((element) => {
    const naturalTop = element.getBoundingClientRect().top;
    window.scrollTo({ top: naturalTop + 260, behavior: "instant" });
  });
  await settleFrames(page);
  const geometry = await page.locator(".pmDetailTabs").evaluate((element) => {
    const rect = element.getBoundingClientRect(), style = getComputedStyle(element);
    const selected = element.querySelector('[aria-selected="true"]').getBoundingClientRect();
    const ancestors = [];
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      const computed = getComputedStyle(parent);
      ancestors.push({ tag: parent.tagName, className: parent.className, overflow: `${computed.overflowX}/${computed.overflowY}`, contain: computed.contain });
    }
    return { scrollY, top: rect.top, safeTop: Number.parseFloat(style.top), position: style.position, activeVisible: selected.left >= rect.left - 1 && selected.right <= rect.right + 1, ancestors };
  });
  assert.ok(geometry.scrollY >= 200, `${description} must scroll the real page beyond 200px`);
  assert.equal(geometry.position, "sticky");
  assert.ok(Math.abs(geometry.top - geometry.safeTop) <= 1.5, `${description} tabs must stay at the safe-area top after deep scrolling: ${JSON.stringify(geometry)}`);
  assert.equal(geometry.activeVisible, true, `${description} selected tab must remain horizontally visible while sticky`);
};
const mobileTabs = ["概览", "预算与现金流", "合同与附件", "进度记录", "成员与权限", "管理记录"];

async function runMobileChecks() {
  const sizes = [[320, 740], [360, 800], [375, 812], [390, 844], [430, 932], [667, 375], [844, 390]];
  for (const [width, height] of sizes) {
    const context = await browser.newContext({ viewport: { width, height }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, reducedMotion: width === 430 ? "reduce" : "no-preference" });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("http://127.0.0.1:4182/tests/project-management-ui.html?mobile_shell=1&large_amounts=1", { waitUntil: "domcontentloaded" });
    await page.getByRole("table", { name: "项目列表" }).waitFor();
    await page.screenshot({ path: path.join(mobileScreenshots, `overview-${width}x${height}-initial-viewport.png`) });
    const filterToggle = page.getByRole("button", { name: "筛选项目", exact: true });
    await filterToggle.waitFor();
    assert.equal(await filterToggle.getAttribute("aria-expanded"), "false");
    assert.equal(await page.getByLabel("按负责人筛选", { exact: true }).isVisible(), false);
    await tap(filterToggle);
    assert.equal(await filterToggle.getAttribute("aria-expanded"), "true");
    await page.getByLabel("按负责人筛选", { exact: true }).selectOption("owner-1");
    await page.getByLabel("按年份筛选", { exact: true }).selectOption("2026");
    await mobileFields(page);
    await tap(filterToggle);
    assert.equal(await page.getByLabel("按负责人筛选", { exact: true }).isVisible(), false);
    assert.match(await page.locator(".pmFilterSummary").innerText(), /观棋/);
    assert.match(await page.locator(".pmFilterSummary").innerText(), /2026/);
    await page.getByLabel("搜索项目", { exact: true }).fill("KPL");
    await noOverflow(page);
    const project = page.getByRole("button", { name: `查看项目 ${projectName}`, exact: true });
    await tap(project);
    await page.getByRole("heading", { name: projectName, exact: true }).waitFor();
    await noOverflow(page);
    assert.match(await page.locator(".pmWorkspaceMetrics").innerText(), /1,234,567,890\.99/);
    for (const amount of await page.locator(".pmWorkspaceMetrics strong").all()) {
      assert.equal(await amount.evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, "Large currency amounts must remain readable without clipping");
    }
    await page.screenshot({ path: path.join(mobileScreenshots, `detail-${width}x${height}.png`), fullPage: true });
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await settleFrames(page);
    await page.screenshot({ path: path.join(mobileScreenshots, `detail-${width}x${height}-viewport.png`) });
    const contractJump = page.locator(".pmContractNotice").getByRole("button", { name: /^查看合同/ });
    await tap(contractJump);
    const contractsTab = page.getByRole("tab", { name: "合同与附件", exact: true });
    assert.equal(await contractsTab.getAttribute("aria-selected"), "true");
    await page.waitForFunction(() => {
      const tab = document.querySelector('[role=tab][aria-selected=true]');
      const nav = document.querySelector(".pmDetailTabs");
      if (!tab || !nav) return false;
      const t = tab.getBoundingClientRect(), n = nav.getBoundingClientRect();
      return t.left >= n.left - 1 && t.right <= n.right + 1 && n.top >= -1 && n.bottom <= innerHeight;
    });
    await mobileFields(page);
    await page.getByLabel("更新合同状态", { exact: true }).selectOption("signed_received");
    await tap(page.getByRole("button", { name: "保存状态", exact: true }));
    assert.equal(await page.getByLabel("更新合同状态", { exact: true }).inputValue(), "signed_received");
    for (const name of mobileTabs) {
      await tap(page.getByRole("tab", { name, exact: true }));
      assert.equal(await page.getByRole("tab", { name, exact: true }).getAttribute("aria-selected"), "true");
      await noOverflow(page);
      await mobileFields(page);
      if ((width === 390 || width === 667) && (name === "概览" || name === "进度记录")) await checkStickyTabs(page, `${width}x${height} ${name}`);
      if (name === "预算与现金流") {
        assert.equal(await page.locator(".pmCashflowTable").isVisible(), false, "Narrow project content should use cashflow cards, including landscape navigation layouts");
        assert.equal(await page.getByLabel("手机端项目现金流计划").isVisible(), true);
        await page.screenshot({ path: path.join(mobileScreenshots, `finance-${width}x${height}.png`), fullPage: true });
      }
      if (name === "成员与权限") {
        const remove = page.getByRole("button", { name: "移除 协作同事 的协作权限", exact: true });
        await touchTarget(remove, "Remove collaborator");
        const lastAction = page.getByRole("button", { name: "添加协作成员", exact: true });
        await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        const bar = page.getByRole("navigation", { name: "手机主导航", exact: true });
        if (await bar.isVisible()) {
          const target = await lastAction.boundingBox(), barBox = await bar.boundingBox();
          assert.ok(target && barBox && target.y + target.height <= barBox.y, "The bottom navigation must not cover the final form action at the end of the page");
        }
      }
    }
    if (width === 390) {
      await tap(page.getByRole("tab", { name: "进度记录", exact: true }));
      await page.getByLabel("本期完成", { exact: true }).fill("旋转前未提交的执行记录");
      await tap(page.getByRole("tab", { name: "成员与权限", exact: true }));
      for (const viewport of [{ width: 844, height: 390 }, { width, height }]) {
        await page.setViewportSize(viewport);
        await page.waitForFunction(() => {
          const tab = document.querySelector('[role=tab][aria-selected=true]');
          const nav = document.querySelector(".pmDetailTabs");
          if (!tab || !nav) return false;
          const t = tab.getBoundingClientRect(), n = nav.getBoundingClientRect();
          return t.left >= n.left - 1 && t.right <= n.right + 1;
        });
        await noOverflow(page);
        assert.equal(await page.getByRole("tab", { name: "成员与权限", exact: true }).getAttribute("aria-selected"), "true");
      }
      await tap(page.getByRole("tab", { name: "进度记录", exact: true }));
      assert.equal(await page.getByLabel("本期完成", { exact: true }).inputValue(), "旋转前未提交的执行记录", "Rotating the device must preserve the current tab and unfinished form");
    }
    if (width === 390 || width === 667) {
      await tap(page.getByRole("tab", { name: "预算与现金流", exact: true }));
      await tap(page.getByRole("button", { name: "修改计划", exact: true }));
      await mobileFields(page);
      await page.getByLabel("计划金额（元）", { exact: true }).fill("480000.25");
      await tap(page.getByRole("button", { name: "保存修改", exact: true }));
      await page.getByRole("status").filter({ hasText: "计划已更新" }).waitFor();
      assert.match(await page.getByLabel("手机端项目现金流计划").innerText(), /480,000\.25/);
      await tap(page.getByRole("button", { name: "编辑项目", exact: true }));
      await page.waitForFunction(() => {
        const summary = document.querySelector(".pmProjectControlPanel > summary");
        const field = document.querySelector('.pmProjectControlPanel input[name="project_no"]');
        const tabs = document.querySelector(".pmDetailTabs");
        if (!summary || !field || !tabs) return false;
        const s = summary.getBoundingClientRect(), f = field.getBoundingClientRect(), t = tabs.getBoundingClientRect();
        return s.top >= t.bottom - 1 && f.top >= t.bottom && f.bottom < innerHeight;
      });
      const summary = page.locator(".pmProjectControlPanel > summary");
      await summary.tap();
      assert.equal(await page.locator(".pmProjectControlPanel").getAttribute("open"), null);
      await summary.tap();
      assert.notEqual(await page.locator(".pmProjectControlPanel").getAttribute("open"), null);
      await page.locator(".pmProjectControlPanel [name=client_contact]").fill("手机端项目对接人");
      await tap(page.getByRole("button", { name: "保存项目修改", exact: true }));
      await page.waitForFunction(() => document.querySelector('[data-testid="updated-contract-status"]')?.textContent === "signed_received");
      await tap(page.getByRole("tab", { name: "进度记录", exact: true }));
      await page.getByLabel("本期完成", { exact: true }).fill("移动端已完成场地核对");
      await page.getByLabel("下一步", { exact: true }).fill("确认执行日程");
      await tap(page.getByRole("button", { name: "保存进度", exact: true }));
      await page.getByRole("status").filter({ hasText: "项目进度已更新" }).waitFor();
    }
    await tap(page.getByRole("button", { name: "全部项目", exact: true }));
    assert.equal(await page.getByLabel("搜索项目", { exact: true }).inputValue(), "KPL");
    assert.equal(await filterToggle.getAttribute("aria-expanded"), "false");
    await tap(filterToggle);
    assert.equal(await page.getByLabel("按负责人筛选", { exact: true }).inputValue(), "owner-1");
    assert.equal(await page.getByLabel("按年份筛选", { exact: true }).inputValue(), "2026");
    await tap(filterToggle);
    await page.screenshot({ path: path.join(mobileScreenshots, `overview-${width}x${height}.png`), fullPage: true });
    await page.getByRole("heading", { name: "项目管理", exact: true }).last().evaluate((element) => element.scrollIntoView({ block: "start" }));
    await page.screenshot({ path: path.join(mobileScreenshots, `overview-${width}x${height}-viewport.png`) });
    await tap(page.getByRole("button", { name: "＋ 新建项目", exact: true }));
    await page.getByLabel("项目名称", { exact: true }).waitFor();
    await noOverflow(page);
    await mobileFields(page);
    if (width === 390) {
      const form = page.locator(".pmCreatePanel form");
      for (const [name, value] of Object.entries({ project_no: "CC26B99", name: "移动端新建项目", company_name: "测试签约主体", client: "测试客户公司", client_contact: "测试对接人", business_category: "电竞培训", planned_start: "2026-10-24", planned_end: "2026-11-24", members: "测试执行同事", objective: "从移动端建立草稿并确认表单可操作" })) {
        await form.locator(`[name="${name}"]`).fill(value);
      }
      await tap(page.getByRole("button", { name: "建立项目草稿", exact: true }));
      await page.waitForFunction(() => document.querySelector('[data-testid="created-project-name"]')?.textContent === "移动端新建项目");
      await page.getByRole("button", { name: "查看项目 移动端新建项目", exact: true }).waitFor();
    }
    await context.close();
  }
}

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:4182/tests/project-management-ui.html", { waitUntil: "domcontentloaded" });
  const table = page.getByRole("table", { name: "项目列表" });
  await table.waitFor();
  assert.equal(await table.getByRole("row").count(), 18);
  await page.screenshot({ path: path.join(screenshots, "overview-all-desktop.png"), fullPage: true });
  await page.getByRole("button", { name: "＋ 新建项目", exact: true }).click();
  await page.getByLabel("项目名称", { exact: true }).waitFor();
  await page.locator(".pmCreatePanel > summary").click();
  await page.locator(".pmCreatePanel").waitFor({ state: "hidden" });
  await page.getByLabel("搜索项目", { exact: true }).fill("CC26B10");
  assert.equal(await table.getByRole("row").count(), 2);
  assert.match(await table.innerText(), new RegExp(projectName));
  assert.match(await table.innerText(), new RegExp(clientName));
  await page.getByLabel("搜索项目", { exact: true }).fill("不存在的项目");
  assert.equal(await page.getByRole("button", { name: /^查看项目 / }).count(), 0);
  await page.getByLabel("搜索项目", { exact: true }).fill("");
  await page.getByLabel("按负责人筛选", { exact: true }).selectOption({ label: "高亚凡" });
  await page.getByLabel("按年份筛选", { exact: true }).selectOption("2025");
  assert.equal(await page.getByRole("button", { name: /^查看项目 / }).count(), 1);
  await page.getByRole("button", { name: /^立项准备/ }).click();
  assert.match(await table.innerText(), /2025电竞场馆立项准备项目/);
  await page.getByRole("button", { name: /^进行中/ }).click();
  assert.equal(await page.getByRole("button", { name: /^查看项目 / }).count(), 0);
  await page.getByLabel("按年份筛选", { exact: true }).selectOption("2026");
  await page.getByLabel("按负责人筛选", { exact: true }).selectOption({ label: "观棋" });
  const lastProject = page.getByRole("button", { name: "查看项目 区域赛事运营与青训项目 11", exact: true });
  await lastProject.scrollIntoViewIfNeeded();
  const listY = await page.evaluate(() => window.scrollY);
  assert.ok(listY > 200, "Use a scrolled list to verify return-position restoration");
  await openProject(page, "区域赛事运营与青训项目 11");
  assert.equal(await table.count(), 0, "The list and project detail must not squeeze each other side by side");
  await page.getByRole("button", { name: "全部项目", exact: true }).click();
  await table.waitFor();
  await page.waitForFunction((position) => Math.abs(window.scrollY - position) < 100, listY);
  assert.equal(await page.getByLabel("按年份筛选", { exact: true }).inputValue(), "2026");
  assert.equal(await page.getByLabel("按负责人筛选", { exact: true }).locator("option:checked").innerText(), "观棋");
  await page.getByLabel("搜索项目", { exact: true }).fill("KPL");
  await page.screenshot({ path: path.join(screenshots, "overview-desktop.png"), fullPage: true });
  await openProject(page);
  await noOverflow(page);
  assert.equal(await page.getByRole("tab", { name: "概览", exact: true }).getAttribute("aria-selected"), "true");
  await page.getByRole("tab", { name: "概览", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.getByRole("tab", { name: "预算与现金流", exact: true }).getAttribute("aria-selected"), "true");
  await page.keyboard.press("Home");
  assert.equal(await page.getByRole("tab", { name: "概览", exact: true }).getAttribute("aria-selected"), "true");
  assert.match(await page.locator(".pmWorkspaceDetail").innerText(), new RegExp(clientName));
  await page.getByRole("tab", { name: "预算与现金流", exact: true }).click();
  assert.match(await page.locator(".pmProcessFinanceSummary article.received strong").innerText(), /10,000\.00/);
  assert.doesNotMatch(await page.locator(".pmProcessFinanceSummary article.received strong").innerText(), /12,000\.00/, "Actual receipts must preserve the confirmed-bank source");
  await page.getByRole("tab", { name: "概览", exact: true }).click();
  await page.screenshot({ path: path.join(screenshots, "detail-desktop.png"), fullPage: true });
  await page.getByRole("tab", { name: "成员与权限", exact: true }).click();
  await page.getByText("协作编辑账号", { exact: true }).waitFor();
  assert.match(await page.locator(".pmExecutionTeam").innerText(), /郑睿/);
  await page.getByPlaceholder("输入同事登录账号", { exact: true }).fill("assistant");
  await page.getByRole("button", { name: "添加协作成员", exact: true }).click();
  await page.locator(".pmCollaboratorChips").getByText("新增协作同事", { exact: true }).waitFor();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "移除 新增协作同事 的协作权限", exact: true }).click();
  assert.match(await page.locator(".pmCollaboratorChips").innerText(), /新增协作同事/);
  await page.getByRole("tab", { name: "预算与现金流", exact: true }).click();
  await page.getByRole("heading", { name: "应收应付与资金周期", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "修改计划", exact: true }).count(), 1, "The visible plan editor preserves the owner permission");
  await page.getByRole("tab", { name: "合同与附件", exact: true }).click();
  await page.getByLabel("更新合同状态", { exact: true }).selectOption("signed_received");
  await page.getByRole("button", { name: "保存状态", exact: true }).click();
  assert.equal(await page.getByLabel("更新合同状态", { exact: true }).inputValue(), "signed_received");
  await page.getByRole("button", { name: "编辑项目", exact: true }).click();
  assert.equal(await page.locator(".pmProjectControlPanel [name=contract_status]").inputValue(), "signed_received");
  await page.locator(".pmProjectControlPanel [name=client_contact]").fill("郑 · 项目对接");
  await page.getByRole("button", { name: "保存项目修改", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "全部项目", exact: true }).isDisabled(), true, "Saving must prevent navigation to a different project");
  assert.equal(await page.getByLabel("切换项目", { exact: true }).isDisabled(), true, "Saving must prevent a project switch until refresh completes");
  await page.waitForFunction(() => document.querySelector('[data-testid="updated-contract-status"]')?.textContent === "signed_received");
  assert.equal(await page.getByTestId("updated-contract-status").textContent(), "signed_received", "Editing project details must not revert a newly signed contract");
  assert.equal(await page.getByRole("button", { name: "全部项目", exact: true }).isDisabled(), false);
  assert.equal(await page.getByLabel("切换项目", { exact: true }).isDisabled(), false);
  await page.getByRole("tab", { name: "进度记录", exact: true }).click();
  await page.getByLabel("完成度", { exact: true }).fill("45");
  await page.getByLabel("本期完成", { exact: true }).fill("训练场地准备完成");
  await page.getByLabel("下一步", { exact: true }).fill("开始集中训练");
  await page.getByRole("tab", { name: "成员与权限", exact: true }).click();
  await page.getByRole("tab", { name: "进度记录", exact: true }).click();
  assert.equal(await page.getByLabel("本期完成", { exact: true }).inputValue(), "训练场地准备完成", "Switching detail tabs must preserve an unfinished form");
  await page.getByRole("button", { name: "保存进度", exact: true }).click();
  await page.getByText("项目进度已更新", { exact: true }).waitFor();
  await page.getByRole("tab", { name: "管理记录", exact: true }).click();
  await page.locator(".pmProjectAdminFooter").getByText("管理记录", { exact: true }).waitFor();
  await page.getByRole("tab", { name: "概览", exact: true }).click();
  await page.getByLabel("切换项目", { exact: true }).selectOption("project-beta");
  await page.getByRole("heading", { name: "2026英雄联盟无畏新生试炼场", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "编辑项目", exact: true }).count(), 0, "Another manager's project must not expose owner editing");
  assert.equal(await page.getByRole("tab", { name: "概览", exact: true }).getAttribute("aria-selected"), "true");
  await page.getByLabel("切换项目", { exact: true }).selectOption("project-alpha");
  await page.getByRole("heading", { name: projectName, exact: true }).waitFor();

  for (const width of [985, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow(page);
    await page.screenshot({ path: path.join(screenshots, `detail-${width}.png`), fullPage: true });
    for (const [key, name] of [["finance", "预算与现金流"], ["contracts", "合同与附件"], ["progress", "进度记录"], ["members", "成员与权限"], ["management", "管理记录"]]) {
      await page.getByRole("tab", { name, exact: true }).click();
      if (key === "management") {
        for (const details of await page.locator(".pmProjectAdminFooter > details").all()) {
          if ((await details.getAttribute("open")) === null) await details.locator(":scope > summary").click();
        }
      }
      await noOverflow(page);
      await page.screenshot({ path: path.join(screenshots, `${key}-${width}.png`), fullPage: true });
    }
    await page.getByRole("button", { name: "全部项目", exact: true }).click();
    await noOverflow(page);
    await page.getByLabel("搜索项目", { exact: true }).fill("KPL");
    const projectButton = page.getByRole("button", { name: `查看项目 ${projectName}`, exact: true });
    assert.equal(await projectButton.evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, "Long project names must wrap within the available width");
    await page.screenshot({ path: path.join(screenshots, `overview-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: "＋ 新建项目", exact: true }).click();
    await page.getByLabel("项目名称", { exact: true }).waitFor();
    await noOverflow(page);
    await page.locator(".pmCreatePanel > summary").click();
    await page.locator(".pmCreatePanel").waitFor({ state: "hidden" });
    await openProject(page);
  }

  await page.setViewportSize({ width: 985, height: 900 });
  for (const contentWidth of [720, 820]) {
    await page.goto(`http://127.0.0.1:4182/tests/project-management-ui.html?content_width=${contentWidth}`, { waitUntil: "domcontentloaded" });
    await table.waitFor();
    await noOverflow(page);
    assert.equal(await page.locator(".pmWorkspaceV2").evaluate((element) => element.clientWidth), contentWidth);
    await page.screenshot({ path: path.join(screenshots, `overview-content-${contentWidth}.png`), fullPage: true });
    await openProject(page);
    for (const name of ["概览", "预算与现金流", "合同与附件", "进度记录", "成员与权限", "管理记录"]) {
      await page.getByRole("tab", { name, exact: true }).click();
      await noOverflow(page);
    }
    await page.getByRole("tab", { name: "概览", exact: true }).click();
    await page.screenshot({ path: path.join(screenshots, `detail-content-${contentWidth}.png`), fullPage: true });
  }

  await page.setViewportSize({ width: 360, height: 900 });
  await page.goto("http://127.0.0.1:4182/tests/project-management-ui.html?fail=1", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: `查看项目 ${projectName}`, exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "项目暂时无法加载，请重试" }).waitFor();
  assert.equal(await page.getByRole("heading", { name: projectName, exact: true }).count(), 0, "A failed selection must not open the wrong project detail");
  await openProject(page);

  await page.goto("http://127.0.0.1:4182/tests/project-management-ui.html?viewer=1", { waitUntil: "domcontentloaded" });
  await openProject(page);
  assert.equal(await page.getByRole("button", { name: "编辑项目", exact: true }).count(), 0);
  await page.getByRole("tab", { name: "成员与权限", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "添加协作成员", exact: true }).count(), 0);
  assert.equal(await page.getByRole("button", { name: /的协作权限$/ }).count(), 0);
  await page.getByRole("tab", { name: "合同与附件", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "保存状态", exact: true }).count(), 0);
  await page.getByRole("tab", { name: "预算与现金流", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "修改计划", exact: true }).count(), 0);
  await page.getByRole("tab", { name: "进度记录", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "保存进度", exact: true }).count(), 0);

  await page.goto("http://127.0.0.1:4182/tests/project-management-ui.html?founder=1", { waitUntil: "domcontentloaded" });
  await openProject(page);
  await page.getByRole("tab", { name: "预算与现金流", exact: true }).click();
  await page.getByRole("button", { name: "确认实际收付", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "修改计划", exact: true }).count(), 0, "Finance confirmation does not grant project-manager editing");
  await runMobileChecks();
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: "passed", checks: "search, intersecting filters, detail/back scroll, keyboard and preserved forms, project switch, confirmed bank amounts, owner writes, contract preservation, save navigation lock, readonly permissions, selection retry, desktop and touch mobile portrait/landscape, folded filters, 44px targets, 16px inputs, large amounts, form saves, real shell and bottom navigation", screenshots, mobileScreenshots }));
} finally {
  await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
  fs.rmSync(outDir, { recursive: true, force: true });
}
