import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build, preview } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "jaos-home-ui-"));
const screenshots = path.join(os.tmpdir(), "jaos-home-ui-screenshots");
fs.mkdirSync(screenshots, { recursive: true });
await build({ configFile: false, plugins: [react()], build: { outDir, rollupOptions: { input: "tests/workspace-home.html" } } });
const server = await preview({ configFile: false, build: { outDir }, preview: { host: "127.0.0.1", port: 4188, strictPort: true } });
const browser = await chromium.launch({ executablePath: process.env.JAOS_BROWSER_EXECUTABLE || (fs.existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : chromium.executablePath()), headless: true, args: ["--no-sandbox"] });
const baseUrl = "http://127.0.0.1:4188/tests/workspace-home.html";
const errors = [];
const frames = async (page) => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const noOverflow = async (page, description) => {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `${description}: document must fit the viewport`);
  for (const selector of [".content", ".homeWorkspace"]) {
    assert.equal(await page.locator(selector).evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, `${description}: ${selector} must fit available width`);
  }
};
const touchTarget = async (target, description) => {
  const box = await target.boundingBox();
  assert.ok(box && box.width >= 43.5 && box.height >= 43.5, `${description}: control needs a 44px target: ${JSON.stringify(box)}`);
};
const lastAction = async (page, value) => page.waitForFunction((expected) => document.querySelector('[data-testid="last-action"]')?.textContent === expected, value);
const installErrorCollector = (page) => page.on("pageerror", (error) => errors.push(error.message));
const home = (page) => page.locator(".homeWorkspace");
const input = (page) => home(page).getByRole("searchbox", { name: "检索知识资料", exact: true });
const metric = (page, label) => home(page).locator(".homeMetricCard").filter({ has: page.getByText(label, { exact: true }) });
const metricValue = async (page, label) => metric(page, label).locator(".homeMetricValue").innerText();
const backHome = async (page) => { await page.getByRole("button", { name: "返回工作台", exact: true }).click(); await home(page).waitFor(); };
const goHome = async (page, query = "") => { await page.goto(`${baseUrl}${query}`, { waitUntil: "domcontentloaded" }); await home(page).waitFor(); await frames(page); };
const readableValues = async (page, description) => {
  for (const value of await home(page).locator(".homeMetricValue, .homeProjectName, .homeProjectDescription, .homeProjectMeta > strong").all()) {
    if (!await value.isVisible()) continue;
    assert.equal(await value.evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, `${description}: complete numbers and names must remain readable: ${await value.innerText()}`);
    assert.notEqual(await value.evaluate((element) => getComputedStyle(element).textOverflow), "ellipsis", `${description}: important names and values must not be replaced by ellipses`);
    if (await value.evaluate((element) => element.classList.contains("homeMetricValue"))) {
      const lines = await value.evaluate((element) => { const range = document.createRange(); range.selectNodeContents(element); return Array.from(range.getClientRects()).filter((rect) => rect.width > 0 && rect.height > 0).length; });
      assert.equal(lines, 1, `${description}: each metric number must stay complete on one line: ${await value.innerText()}`);
    }
  }
};
const waitSearchComplete = async (page, query) => {
  await home(page).getByRole("region", { name: "检索结果", exact: true }).getByRole("button", { name: "查看完整结果", exact: true }).waitFor();
  assert.match(await page.getByTestId("search-answer").innerText(), new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
};

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  installErrorCollector(page);
  await goHome(page);
  await home(page).waitFor();
  await frames(page);
  await noOverflow(page, "desktop founder home");
  await readableValues(page, "desktop founder home");
  assert.equal(await home(page).locator(".homeMetricCard").count(), 4);
  assert.equal(await metricValue(page, "可见资料项目"), "6");
  assert.equal(await metricValue(page, "登记文件"), "5,184");
  assert.equal(await metricValue(page, "原件可用"), "5,088");
  assert.equal(await metricValue(page, "当前版本文件"), "1");
  assert.match(await metric(page, "当前版本文件").innerText(), /已发布的当前版本/);
  assert.doesNotMatch(await home(page).innerText(), /未经批准保持为\s*0|可检索文件|最新候选项目/);
  assert.equal(await home(page).locator(".homeProjectRow").count(), 5, "Project panel displays at most five visible projects");
  assert.equal(await home(page).getByText("不应出现在前五条中的历史项目", { exact: true }).count(), 0);
  for (const status of ["候选资料", "已入库", "当前版本", "历史版本"]) assert.ok(await home(page).getByText(status, { exact: true }).count() > 0, `Project library keeps mixed knowledge state: ${status}`);
  assert.match(await home(page).locator(".homeProjectRow").first().innerText(), /本地示例文化传播与赛事运营有限公司.*2026 年/s);
  assert.equal(await home(page).getByRole("button", { name: "检索资料", exact: true }).isDisabled(), true, "Blank search cannot submit");
  await page.screenshot({ path: path.join(screenshots, "desktop-home.png"), fullPage: true });
  await page.screenshot({ path: path.join(screenshots, "desktop-home-viewport.png") });

  await home(page).getByRole("button", { name: "查看全部资料", exact: true }).click();
  await lastAction(page, "navigate:AI资料检索");
  await backHome(page);
  for (const [title, target] of [["AI资料检索", "AI资料检索"], ["用智库写材料", "智能创作"], ["处理入库资料", "入库审核"]]) {
    await home(page).locator(".homeTaskButton").filter({ hasText: title }).click();
    await lastAction(page, `navigate:${target}`);
    await backHome(page);
  }
  const sample = home(page).getByRole("button", { name: "训练营方案", exact: true });
  await sample.click();
  assert.equal(await input(page).inputValue(), "训练营方案");
  assert.equal(await input(page).evaluate((element) => element === document.activeElement), true, "Examples focus the search field");
  assert.equal(await page.getByTestId("search-count").innerText(), "0", "Examples fill the query without requesting a search");
  await home(page).getByRole("button", { name: "清空检索内容", exact: true }).click();
  assert.equal(await input(page).inputValue(), "");
  await input(page).fill("   ");
  assert.equal(await home(page).getByRole("button", { name: "检索资料", exact: true }).isDisabled(), true);
  await input(page).fill("训练营课程安排");
  await input(page).press("Enter");
  await lastAction(page, "search:训练营课程安排");
  const result = home(page).getByRole("region", { name: "检索结果", exact: true });
  assert.equal(await result.getAttribute("aria-busy"), "true");
  assert.equal(await home(page).getByRole("button", { name: "检索中…", exact: true }).isDisabled(), true);
  assert.equal(await input(page).isDisabled(), true);
  assert.equal(await home(page).getByRole("button", { name: "训练营方案", exact: true }).isDisabled(), true);
  assert.equal(await home(page).locator(".homeProjectButton").first().isDisabled(), true, "Project shortcuts cannot start another search while busy");
  await home(page).locator("form.homeSearchForm").evaluate((form) => form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  assert.equal(await page.getByTestId("search-count").innerText(), "1", "Busy state prevents duplicate submits");
  await waitSearchComplete(page, "训练营课程安排");
  assert.equal(await result.getAttribute("aria-busy"), "false");
  assert.match(await result.innerText(), /3 份相关资料/);
  await readableValues(page, "desktop search results");
  await result.getByRole("button", { name: "查看完整结果", exact: true }).click();
  await lastAction(page, "navigate:AI资料检索");
  await backHome(page);

  const project = home(page).locator(".homeProjectRow").first();
  const projectName = await project.locator(".homeProjectName").innerText();
  await project.getByRole("button", { name: `检索项目资料：${projectName}`, exact: true }).click();
  await lastAction(page, `search:${projectName}`);
  assert.equal(await page.getByTestId("requested-query").innerText(), projectName, "Project selection sends its own complete name, never the previous input state");
  assert.equal(await input(page).inputValue(), projectName);
  assert.equal(await page.getByTestId("search-answer").count(), 0, "Old answer is hidden while a different search is running");
  await waitSearchComplete(page, projectName);
  await input(page).fill("失败测试");
  await home(page).getByRole("button", { name: "检索资料", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "检索暂时不可用" }).waitFor();
  assert.equal(await input(page).inputValue(), "失败测试", "Failed searches retain the question for retry");
  assert.equal(await home(page).getByRole("button", { name: "检索资料", exact: true }).isEnabled(), true);
  await input(page).fill("恢复检索");
  await input(page).press("Enter");
  await waitSearchComplete(page, "恢复检索");

  await goHome(page, "?loading");
  assert.deepEqual(await home(page).locator(".homeMetricValue").allTextContents(), ["—", "—", "—", "—"], "Unknown loading values must not be shown as zeros");
  assert.equal(await home(page).locator(".homeProjectRow").count(), 0);
  await home(page).getByRole("status").filter({ hasText: "正在加载项目资料" }).waitFor();
  await goHome(page, "?unknown_counts");
  for (const label of ["登记文件", "原件可用", "当前版本文件"]) {
    assert.equal(await metricValue(page, label), "—");
    assert.match(await metric(page, label).innerText(), /统计暂未提供/);
  }
  await goHome(page, "?zero_counts&empty");
  assert.deepEqual(await home(page).locator(".homeMetricValue").allTextContents(), ["0", "0", "0", "0"], "Known zero values remain distinct from unknown");
  assert.match(await metric(page, "当前版本文件").innerText(), /尚未发布当前版本/);
  await home(page).getByRole("button", { name: "去上传资料", exact: true }).click();
  await lastAction(page, "navigate:资料上传");

  await goHome(page, "?employee");
  assert.equal(await home(page).locator(".homeMetricCard").count(), 2);
  assert.equal(await metricValue(page, "可见资料项目"), "6");
  assert.equal(await metricValue(page, "项目内可见文件"), "51");
  for (const label of ["登记文件", "原件可用", "当前版本文件", "待处理入库资料"]) assert.equal(await metric(page, label).count(), 0, `Employee home must not render global/reviewer statistics: ${label}`);
  assert.equal(await home(page).locator(".homeTaskButton").filter({ hasText: "处理入库资料" }).count(), 0);
  await home(page).locator(".homeTaskButton").filter({ hasText: "上传工作资料" }).click();
  await lastAction(page, "navigate:资料上传");
  await goHome(page, "?reviewer");
  assert.equal(await home(page).locator(".homeMetricCard").count(), 3);
  assert.equal(await metricValue(page, "待处理入库资料"), "128");
  assert.equal(await metricValue(page, "项目内可见文件"), "51");
  for (const label of ["登记文件", "原件可用", "当前版本文件"]) assert.equal(await metric(page, label).count(), 0);
  await goHome(page, "?zero_reviews");
  assert.match(await home(page).locator(".homeTaskButton").filter({ hasText: "处理入库资料" }).innerText(), /当前队列暂无待处理资料/);

  await goHome(page, "?busy&query=新问题");
  assert.equal(await home(page).getByRole("region", { name: "检索结果", exact: true }).getAttribute("aria-busy"), "true");
  assert.equal(await page.getByTestId("search-answer").count(), 0, "Pre-existing results stay hidden for an in-flight query");
  assert.equal(await home(page).getByRole("button", { name: "查看完整结果", exact: true }).count(), 0);

  await goHome(page, "?large_counts");
  assert.equal(await metricValue(page, "登记文件"), "1,234,567,890");
  await readableValues(page, "large desktop metrics");
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.evaluate(() => localStorage.removeItem("jaos-navigation-mode"));
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector(".workspaceSidebar")?.getBoundingClientRect().width === 80);
  await noOverflow(page, "tablet automatic rail");
  await readableValues(page, "tablet automatic rail");
  await page.getByRole("complementary", { name: "桌面导航栏" }).getByRole("button", { name: "展开导航", exact: true }).click();
  await page.waitForFunction(() => document.querySelector(".workspaceSidebar")?.getBoundingClientRect().width === 256);
  await noOverflow(page, "tablet expanded sidebar");
  await readableValues(page, "tablet expanded sidebar");
  console.log("Home desktop workflows passed: accurate metrics, roles, search and project queries, retry and sidebar widths");

  for (const [width, height] of [[320, 740], [360, 800], [390, 844], [430, 932], [667, 375]]) {
    const context = await browser.newContext({ viewport: { width, height }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
    const mobile = await context.newPage();
    installErrorCollector(mobile);
    await goHome(mobile);
    await home(mobile).waitFor();
    await frames(mobile);
    await noOverflow(mobile, `mobile home ${width}x${height}`);
    await readableValues(mobile, `mobile home ${width}x${height}`);
    assert.equal(await mobile.getByRole("navigation", { name: "手机端主导航" }).isVisible(), true);
    assert.ok(await input(mobile).evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize)) >= 16, "Mobile search input should not trigger iOS text zoom");
    await touchTarget(input(mobile), `Mobile ${width} search input`);
    for (const button of await home(mobile).getByRole("button").all()) {
      if (!await button.isVisible()) continue;
      await button.scrollIntoViewIfNeeded();
      await touchTarget(button, `Mobile ${width} ${await button.getAttribute("aria-label") || await button.innerText()}`);
      assert.equal(await button.evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, "Mobile controls keep complete labels");
    }
    await mobile.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await frames(mobile);
    await mobile.screenshot({ path: path.join(screenshots, `mobile-home-${width}x${height}.png`), fullPage: true });
    await mobile.screenshot({ path: path.join(screenshots, `mobile-home-${width}x${height}-viewport.png`) });
    await home(mobile).getByRole("button", { name: "赛事执行清单", exact: true }).scrollIntoViewIfNeeded();
    await home(mobile).getByRole("button", { name: "赛事执行清单", exact: true }).tap();
    assert.equal(await input(mobile).inputValue(), "赛事执行清单");
    assert.equal(await mobile.getByTestId("search-count").innerText(), "0");
    await home(mobile).getByRole("button", { name: "检索资料", exact: true }).scrollIntoViewIfNeeded();
    await home(mobile).getByRole("button", { name: "检索资料", exact: true }).tap();
    await waitSearchComplete(mobile, "赛事执行清单");
    await noOverflow(mobile, `mobile result ${width}x${height}`);
    await home(mobile).getByRole("button", { name: "清空检索内容", exact: true }).scrollIntoViewIfNeeded();
    await home(mobile).getByRole("button", { name: "清空检索内容", exact: true }).tap();
    assert.equal(await input(mobile).inputValue(), "");
    const mobileProject = home(mobile).locator(".homeProjectRow").first();
    const mobileProjectName = await mobileProject.locator(".homeProjectName").innerText();
    await mobileProject.getByRole("button").scrollIntoViewIfNeeded();
    await mobileProject.getByRole("button").tap();
    await lastAction(mobile, `search:${mobileProjectName}`);
    await waitSearchComplete(mobile, mobileProjectName);
    assert.equal(await mobile.getByTestId("requested-query").innerText(), mobileProjectName);
    await context.close();
    console.log(`Home touch viewport ${width}x${height} passed`);
  }

  const small = await browser.newPage({ viewport: { width: 320, height: 740 } });
  installErrorCollector(small);
  await goHome(small, "?large_counts&long_names");
  await home(small).waitFor();
  await noOverflow(small, "320px large counts and long project names");
  await readableValues(small, "320px large counts and long project names");
  assert.equal(await metricValue(small, "登记文件"), "1,234,567,890");
  await small.screenshot({ path: path.join(screenshots, "mobile-long-names-large-counts.png"), fullPage: true });
  for (const role of ["employee", "reviewer"]) {
    await goHome(small, `?${role}&long_names`);
    await noOverflow(small, `320px ${role} home`);
    await readableValues(small, `320px ${role} home`);
    assert.equal(await home(small).locator(".homeMetricCard").count(), role === "employee" ? 2 : 3);
  }

  // This path mounts the actual application, not just its home component. All
  // reads and searches are local mocks; the token is a deliberately fake value.
  const actual = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  installErrorCollector(actual);
  const unexpectedReads = [], searchPayloads = [];
  const actualProjects = ["实际首页集成项目甲", "实际首页集成项目乙"];
  await actual.addInitScript(() => sessionStorage.setItem("jingao-kb-session", "local-home-integration-only"));
  await actual.route("**/api/kb/**", async (route) => {
    const url = new URL(route.request().url());
    const endpoint = url.pathname.replace("/api/kb/", "");
    if (endpoint === "v1/me") return route.fulfill({ json: { id: "local-home-integration-user", username: "local-home-integration-user", display_name: "本地集成示例同事", role: "employee", organization_role: "business", confidentiality_ceiling: "L2", departments: ["training"] } });
    if (endpoint === "v1/status") return route.fulfill({ json: { status: "ready", environment: "local-fixture", database: "local-mock", retrieval: { exact: true, semantic: false, llm_generation: false, outbound_enabled: false }, counts: { projects: 999, documents: null, chunks: null, current_documents: null, candidate_documents: null, source_available_documents: null, source_missing_documents: null }, policy_version: "local-fixture" } });
    if (endpoint === "v1/categories") return route.fulfill({ json: [{ id: "local-category", key: "training", name: "电竞培训", active: true, sort_order: 1, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z" }] });
    if (endpoint === "v1/projects") return route.fulfill({ json: actualProjects.map((name, index) => ({ id: `local-project-${index}`, name, client: "本地测试公司", year: 2026, domain: "training", status: "active", knowledge_status: "approved", confirmed: true, document_count: index + 2, has_closing_report: true, closing_report_reminder: false })) });
    if (endpoint === "v1/search") {
      const body = route.request().postDataJSON();
      searchPayloads.push(body);
      const more = body.offset > 0;
      if (more) await new Promise((resolve) => setTimeout(resolve, 700));
      const second = body.query === actualProjects[1];
      await route.fulfill({ json: { query_id: "local-query", retrieval_mode: "deterministic", retrieval_degraded: false, scope: "history", scope_reason: "local-fixture", answer: second ? "本地乙项目检索答案" : "本地甲项目检索答案", generation_mode: "deterministic", generation_model: null, generation_fallback_used: false, generation_degraded: false, total: second ? 1 : 2, offset: body.offset, limit: 20, denied_count: 0, unavailable_count: 0, results: [{ document_id: more ? "old-delayed-document" : second ? "second-document" : "first-document", title: more ? "迟到的旧项目资料" : second ? "乙项目引用原文" : "甲项目引用原文", version: "v1", page: 1, citation_basis: "page", project_id: second ? "local-project-1" : "local-project-0", project: body.query, domain: "training", knowledge_status: "approved", confidentiality: "L2", excerpt: "此内容仅用于本地真实首页集成验证。", score: 1 }] } });
      return;
    }
    unexpectedReads.push(`${route.request().method()} ${endpoint}`);
    await route.fulfill({ status: 404, json: { detail: `Unexpected local integration request: ${endpoint}` } });
  });
  await actual.goto(`${baseUrl}?actual_home`, { waitUntil: "domcontentloaded" });
  await home(actual).waitFor();
  assert.equal(await metricValue(actual, "可见资料项目"), "2", "Actual Home uses the visible project response, not status.projects=999");
  assert.equal(await metricValue(actual, "项目内可见文件"), "5");
  for (const label of ["登记文件", "原件可用", "当前版本文件"]) assert.equal(await metric(actual, label).count(), 0, "Actual employee Home cannot expose global totals");
  await input(actual).fill(actualProjects[0]);
  await home(actual).getByRole("button", { name: "检索资料", exact: true }).click();
  await home(actual).getByRole("region", { name: "检索结果", exact: true }).getByText("本地甲项目检索答案", { exact: true }).waitFor();
  assert.deepEqual(searchPayloads[0], { query: actualProjects[0], scope: "auto", limit: 20, offset: 0 }, "Actual Home hero submits the controlled question to the real handler");
  assert.equal(await input(actual).inputValue(), actualProjects[0]);
  await home(actual).getByRole("button", { name: "查看完整结果", exact: true }).click();
  await actual.locator(".fullAnswer").getByRole("heading", { name: "本地甲项目检索答案", exact: true }).waitFor();
  const delayedRequest = actual.waitForRequest((request) => request.url().includes("/api/kb/v1/search") && request.postDataJSON()?.offset > 0);
  const delayedResponse = actual.waitForResponse((response) => response.url().includes("/api/kb/v1/search") && response.request().postDataJSON()?.offset > 0);
  await actual.getByRole("button", { name: "继续显示更多", exact: true }).click();
  await delayedRequest;
  await actual.getByRole("complementary", { name: "桌面导航栏" }).getByRole("button", { name: "工作台", exact: true }).click();
  await input(actual).fill("不应提交的旧关键词");
  await home(actual).getByRole("button", { name: `检索项目资料：${actualProjects[1]}`, exact: true }).click();
  await actual.locator(".fullAnswer").getByRole("heading", { name: "本地乙项目检索答案", exact: true }).waitFor();
  assert.equal(await actual.locator(".questionPanel textarea").inputValue(), actualProjects[1], "Project search navigates directly to full results and keeps the exact selected name");
  await (await delayedResponse).finished();
  await frames(actual);
  await actual.locator(".fullAnswer").getByRole("heading", { name: "本地乙项目检索答案", exact: true }).waitFor();
  assert.equal(await actual.locator(".fullAnswer").getByText("乙项目引用原文", { exact: true }).count(), 1);
  assert.equal(await actual.getByText("迟到的旧项目资料", { exact: true }).count(), 0, "Late load-more from an older project must not join the new search results");
  assert.deepEqual(searchPayloads.at(-1), { query: actualProjects[1], scope: "auto", limit: 20, offset: 0 });
  assert.deepEqual(unexpectedReads, [], "Actual employee Home must only use its authorized mocked reads and search");
  assert.equal(await actual.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, "Actual search destination fits beside the new sidebar");
  console.log("Actual Home integration passed: visible counts, exact project search payload, full results and stale load-more isolation");
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: "passed", checks: "real home and navigation, founder/reviewer/employee scopes, accurate/null/zero metrics, mixed project states and first-five list, controlled search/examples/clear/duplicate guard/results, exact project query, retry retention, empty/library/task routes, full and compact/tablet sidebar geometry, single-line large counts and long names, desktop and 5 touch portrait/landscape sizes, 44px targets and 16px search input, actual Home visible-count/search-payload/full-result integration and stale load-more isolation", screenshots }));
} finally {
  await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
  fs.rmSync(outDir, { recursive: true, force: true });
}
