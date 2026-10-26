import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build, preview } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "jaos-navigation-ui-"));
const screenshots = path.join(os.tmpdir(), "jaos-navigation-ui-screenshots");
fs.mkdirSync(screenshots, { recursive: true });
await build({ configFile: false, plugins: [react()], build: { outDir, rollupOptions: { input: "tests/workspace-navigation.html" } } });
const server = await preview({ configFile: false, build: { outDir }, preview: { host: "127.0.0.1", port: 4187, strictPort: true } });
const browser = await chromium.launch({ executablePath: process.env.JAOS_BROWSER_EXECUTABLE || (fs.existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : chromium.executablePath()), headless: true, args: ["--no-sandbox"] });
const baseUrl = "http://127.0.0.1:4187/tests/workspace-navigation.html";
const errors = [];
const frames = async (page) => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const noOverflow = async (page, description) => {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `${description}: document must fit the viewport`);
  assert.equal(await page.locator(".content").evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, `${description}: content must fit the space beside navigation`);
};
const touchTarget = async (button, description) => {
  const box = await button.boundingBox();
  assert.ok(box && box.width >= 43.5 && box.height >= 43.5, `${description}: action needs a 44px target: ${JSON.stringify(box)}`);
};
const lastAction = async (page, value) => page.waitForFunction((expected) => document.querySelector('[data-testid="last-action"]')?.textContent === expected, value);
const moduleNames = ["工作台", "财务分析", "项目管理", "资料上传", "合同档案库", "AI资料检索", "智能创作", "入库审核", "资料治理", "系统状态", "账号管理"];
const sidebar = (page) => page.getByRole("complementary", { name: "桌面导航栏" });
const desktopModule = (page, name) => sidebar(page).getByRole("navigation", { name: "主导航", exact: true }).getByRole("button", { name: new RegExp(`^${name}`) });
const waitWidth = async (page, width) => page.waitForFunction((expected) => Math.abs(document.querySelector(".workspaceSidebar").getBoundingClientRect().width - expected) <= 1, width);
const contentBesideSidebar = async (page) => {
  const positions = await page.evaluate(() => ({ edge: document.querySelector(".workspaceSidebar").getBoundingClientRect().right, content: document.querySelector(".content").getBoundingClientRect().left }));
  assert.ok(positions.content >= positions.edge - 1, `Content must move with navigation width: ${JSON.stringify(positions)}`);
};
const openMore = async (page, touch = false) => {
  const button = page.getByRole("navigation", { name: "手机端主导航" }).getByRole("button", { name: "更多", exact: true });
  if (touch) await button.tap(); else await button.click();
  await page.getByRole("dialog", { name: "更多功能", exact: true }).waitFor();
  await frames(page);
  return page.getByRole("dialog", { name: "更多功能", exact: true });
};
const dialogClosed = async (page) => {
  await page.getByRole("dialog", { name: "更多功能", exact: true, includeHidden: true }).waitFor({ state: "detached" });
  await page.waitForFunction(() => document.body.style.overflow !== "hidden");
  await page.waitForFunction(() => Array.from(document.querySelector(".workspaceShell")?.children || []).every((element) => !(element instanceof HTMLElement) || !element.inert));
  assert.notEqual(await page.evaluate(() => document.body.style.overflow), "hidden", "Closing More must restore page scrolling");
  assert.deepEqual(await page.locator(".workspaceShell > *").evaluateAll((elements) => elements.filter((element) => element instanceof HTMLElement && element.inert).map((element) => element.className)), [], "Closing More must restore every background element's interactivity");
};

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await sidebar(page).waitFor();
  await frames(page);
  await waitWidth(page, 256);
  await noOverflow(page, "desktop");
  await contentBesideSidebar(page);
  for (const name of moduleNames) assert.equal(await desktopModule(page, name).count(), 1, `Authorized module remains reachable: ${name}`);
  for (const name of ["工作空间", "知识协作", "管理与设置"]) assert.equal(await sidebar(page).getByText(name, { exact: true }).isVisible(), true);
  assert.equal(await desktopModule(page, "工作台").getAttribute("aria-current"), "page");
  assert.equal(await sidebar(page).getByRole("button", { name: /^打开.*账套$/ }).count(), 0, "Unrelated pages should start with company accounts collapsed");
  assert.equal(await sidebar(page).locator('[title="待审核 128 项"]').innerText(), "99+", "Large review queues remain compact while retaining the real total");
  assert.match(await sidebar(page).innerText(), /当前资料不出网/);
  assert.ok(await sidebar(page).locator("svg").count() >= 11, "Navigation uses consistent vector icons");
  await page.screenshot({ path: path.join(screenshots, "desktop-expanded.png") });
  await sidebar(page).screenshot({ path: path.join(screenshots, "desktop-sidebar.png") });

  await sidebar(page).getByRole("button", { name: "展开财务账套", exact: true }).click();
  for (const name of ["京奥电竞", "王牌猎豹", "劲腾豹跃", "星曜电竞"]) await sidebar(page).getByRole("button", { name: `打开${name}账套`, exact: true }).waitFor();
  await sidebar(page).getByRole("button", { name: "打开王牌猎豹账套", exact: true }).click();
  await lastAction(page, "entity:entity-ace");
  assert.equal(await sidebar(page).getByRole("button", { name: "打开王牌猎豹账套", exact: true }).getAttribute("aria-current"), "page");
  assert.equal(await desktopModule(page, "财务分析").getAttribute("aria-current"), "page");
  await page.screenshot({ path: path.join(screenshots, "desktop-finance-accounts.png") });
  await desktopModule(page, "项目管理").click();
  await lastAction(page, "navigate:项目管理");
  assert.equal(await sidebar(page).getByRole("button", { name: /^打开.*账套$/ }).count(), 0, "Leaving finance must release its vertical space");
  await desktopModule(page, "财务分析").click();
  await sidebar(page).getByRole("button", { name: "收起财务账套", exact: true }).waitFor();
  await sidebar(page).getByRole("button", { name: "收起财务账套", exact: true }).click();
  assert.equal(await sidebar(page).getByRole("button", { name: /^打开.*账套$/ }).count(), 0, "Accounts can be collapsed on the active finance page");

  await sidebar(page).getByRole("button", { name: "修改密码", exact: true }).click();
  await lastAction(page, "password");
  await sidebar(page).getByRole("button", { name: "退出登录", exact: true }).click();
  await lastAction(page, "logout");
  await sidebar(page).getByRole("button", { name: "收起导航", exact: true }).click();
  await waitWidth(page, 80);
  await contentBesideSidebar(page);
  await noOverflow(page, "manual compact rail");
  for (const name of moduleNames) {
    const button = desktopModule(page, name);
    await touchTarget(button, `Compact ${name}`);
    assert.equal(await button.getAttribute("title"), name, `Compact icon must reveal its module name: ${name}`);
  }
  await page.screenshot({ path: path.join(screenshots, "desktop-compact.png") });
  await page.reload({ waitUntil: "domcontentloaded" });
  await waitWidth(page, 80);
  assert.equal(await page.evaluate(() => localStorage.getItem("jaos-navigation-mode")), "compact", "Manual rail preference survives reload");
  await sidebar(page).getByRole("button", { name: "展开导航", exact: true }).click();
  await waitWidth(page, 256);
  await contentBesideSidebar(page);
  await page.setViewportSize({ width: 1440, height: 520 });
  await sidebar(page).getByRole("button", { name: "展开财务账套", exact: true }).click();
  const nav = sidebar(page).getByRole("navigation", { name: "主导航", exact: true });
  const pinnedBefore = await sidebar(page).getByRole("button", { name: "退出登录", exact: true }).boundingBox();
  const scrollState = await nav.evaluate((element) => { element.scrollTop = element.scrollHeight; return { scrollTop: element.scrollTop, height: element.clientHeight, content: element.scrollHeight, page: scrollY }; });
  assert.ok(scrollState.content > scrollState.height && scrollState.scrollTop > 0, "Low-height navigation must scroll independently");
  const pinnedAfter = await sidebar(page).getByRole("button", { name: "退出登录", exact: true }).boundingBox();
  assert.ok(Math.abs(pinnedBefore.y - pinnedAfter.y) <= 1, "Account actions remain pinned while navigation scrolls");
  assert.equal(await page.evaluate(() => scrollY), scrollState.page, "Scrolling navigation must not move the workspace");
  await nav.getByRole("button", { name: /^账号管理/ }).scrollIntoViewIfNeeded();
  await nav.getByRole("button", { name: /^账号管理/ }).click();
  await lastAction(page, "navigate:账号管理");

  await page.setViewportSize({ width: 1024, height: 768 });
  // A fresh page tests automatic breakpoint behavior separately from a user's
  // explicit expanded preference.
  await page.evaluate(() => localStorage.removeItem("jaos-navigation-mode"));
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await waitWidth(page, 80);
  await contentBesideSidebar(page);
  await sidebar(page).getByRole("button", { name: "展开导航", exact: true }).click();
  await waitWidth(page, 256);
  await contentBesideSidebar(page);
  await noOverflow(page, "tablet manually expanded");

  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto(`${baseUrl}?restricted`, { waitUntil: "domcontentloaded" });
  for (const name of ["财务分析", "项目管理", "合同档案库", "入库审核", "资料治理", "系统状态", "账号管理"]) {
    assert.equal(await page.getByRole("button", { name: new RegExp(`^${name}`), includeHidden: true }).count(), 0, `Restricted navigation must not mount unauthorized module ${name}`);
  }
  assert.equal(await sidebar(page).getByText("管理与设置", { exact: true }).count(), 0, "Empty permission groups stay absent");
  await noOverflow(page, "restricted desktop");
  await page.goto(`${baseUrl}?empty_entities&zero_reviews&outbound=1`, { waitUntil: "domcontentloaded" });
  assert.equal(await sidebar(page).getByRole("button", { name: /财务账套/ }).count(), 0, "An empty company list must not expose a dead expander");
  assert.equal(await sidebar(page).locator('[title^="待审核 "]').count(), 0, "Zero review queues need no badge");
  assert.match(await sidebar(page).innerText(), /已启用出网/);
  await page.goto(`${baseUrl}?long_names&finance`, { waitUntil: "domcontentloaded" });
  await sidebar(page).getByRole("button", { name: /^打开京奥电竞跨区域/ }).waitFor();
  await noOverflow(page, "long company and account names");
  assert.equal(await sidebar(page).evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, "Long names must remain inside the sidebar");
  await page.screenshot({ path: path.join(screenshots, "desktop-long-names.png") });

  console.log("Desktop navigation passed: grouping, permission boundary, accounts, compact rail and independent scrolling");
  for (const [width, height] of [[320, 740], [390, 844], [430, 932], [667, 375]]) {
    const context = await browser.newContext({ viewport: { width, height }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
    const mobile = await context.newPage();
    mobile.on("pageerror", (error) => errors.push(error.message));
    await mobile.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await mobile.getByRole("navigation", { name: "手机端主导航" }).waitFor();
    await noOverflow(mobile, `mobile ${width}x${height}`);
    assert.equal(await sidebar(mobile).count(), 0, "Desktop sidebar must be hidden from the mobile accessibility tree");
    const primary = mobile.getByRole("navigation", { name: "手机端主导航" });
    assert.equal(await primary.getByRole("button").count(), 5, "Phones retain four primary actions and More");
    for (const button of await primary.getByRole("button").all()) await touchTarget(button, `Mobile ${width} primary navigation`);
    await primary.getByRole("button", { name: "资料检索", exact: true }).tap();
    await lastAction(mobile, "navigate:AI资料检索");
    await mobile.evaluate(() => window.scrollTo({ top: 480, behavior: "instant" }));
    const previousY = await mobile.evaluate(() => scrollY);
    const dialog = await openMore(mobile, true);
    assert.equal(await mobile.evaluate(() => document.body.style.overflow), "hidden", "More locks background page scrolling");
    assert.equal(await mobile.locator(".content").evaluate((element) => element.inert), true, "Background workspace cannot receive focus while More is open");
    assert.equal(await dialog.evaluate((element) => element.contains(document.activeElement)), true, "Opening More puts focus in the dialog");
    await noOverflow(mobile, `mobile More ${width}x${height}`);
    for (const button of await dialog.locator(".workspaceMobileModule").all()) {
      await button.scrollIntoViewIfNeeded();
      await touchTarget(button, `Mobile ${width} module ${await button.innerText()}`);
      assert.equal(await button.evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, "Mobile module labels stay fully inside their buttons");
    }
    const focusable = dialog.locator('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]');
    await focusable.first().focus();
    await mobile.keyboard.press("Shift+Tab");
    assert.equal(await focusable.last().evaluate((element) => element === document.activeElement), true, "Shift+Tab wraps inside More");
    await mobile.keyboard.press("Tab");
    assert.equal(await focusable.first().evaluate((element) => element === document.activeElement), true, "Tab wraps inside More");
    await mobile.keyboard.press("Escape");
    await dialogClosed(mobile);
    assert.equal(await primary.getByRole("button", { name: "更多", exact: true }).evaluate((element) => element === document.activeElement), true, "Escape returns focus to the opener");
    assert.equal(await mobile.evaluate(() => scrollY), previousY, "Closing More preserves workspace scroll position");

    const financeDialog = await openMore(mobile, true);
    await financeDialog.getByRole("button", { name: "打开劲腾豹跃账套", exact: true }).scrollIntoViewIfNeeded();
    await touchTarget(financeDialog.getByRole("button", { name: "打开劲腾豹跃账套", exact: true }), "Mobile company selection");
    await financeDialog.getByRole("button", { name: "打开劲腾豹跃账套", exact: true }).tap();
    await lastAction(mobile, "entity:entity-power");
    await dialogClosed(mobile);
    const selectedDialog = await openMore(mobile, true);
    assert.equal(await selectedDialog.getByRole("button", { name: "打开劲腾豹跃账套", exact: true }).getAttribute("aria-current"), "page");
    await selectedDialog.getByRole("button", { name: "修改密码", exact: true }).scrollIntoViewIfNeeded();
    await touchTarget(selectedDialog.getByRole("button", { name: "修改密码", exact: true }), "Mobile change password");
    await selectedDialog.getByRole("button", { name: "修改密码", exact: true }).tap();
    await lastAction(mobile, "password");
    await dialogClosed(mobile);
    const logoutDialog = await openMore(mobile, true);
    await logoutDialog.getByRole("button", { name: "退出登录", exact: true }).scrollIntoViewIfNeeded();
    await logoutDialog.getByRole("button", { name: "退出登录", exact: true }).tap();
    await lastAction(mobile, "logout");
    await dialogClosed(mobile);
    const closeDialog = await openMore(mobile, true);
    await closeDialog.getByRole("button", { name: "关闭更多功能", exact: true }).tap();
    await dialogClosed(mobile);
    const backdropDialog = await openMore(mobile, true);
    const rect = await backdropDialog.boundingBox();
    assert.ok(rect.y > 3, "More leaves a dismissible backdrop above the sheet");
    await mobile.touchscreen.tap(3, 3);
    await dialogClosed(mobile);

    await mobile.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await mobile.screenshot({ path: path.join(screenshots, `mobile-${width}x${height}.png`) });
    await openMore(mobile, true);
    await mobile.screenshot({ path: path.join(screenshots, `mobile-more-${width}x${height}.png`) });
    await mobile.setViewportSize({ width: 1200, height: 800 });
    await dialogClosed(mobile);
    await sidebar(mobile).waitFor();
    await contentBesideSidebar(mobile);
    await context.close();
    console.log(`Mobile navigation ${width}x${height} passed`);
  }
  const restrictedMobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  restrictedMobile.on("pageerror", (error) => errors.push(error.message));
  await restrictedMobile.goto(`${baseUrl}?restricted`, { waitUntil: "domcontentloaded" });
  const restrictedDialog = await openMore(restrictedMobile);
  for (const name of ["财务分析", "项目管理", "合同档案库", "入库审核", "资料治理", "系统状态", "账号管理"]) {
    assert.equal(await restrictedDialog.getByRole("button", { name: new RegExp(`^${name}`), includeHidden: true }).count(), 0, `Restricted mobile navigation must not offer ${name}`);
  }
  await restrictedDialog.getByRole("button", { name: "关闭更多功能", exact: true }).click();
  await dialogClosed(restrictedMobile);
  await restrictedMobile.setViewportSize({ width: 320, height: 740 });
  await restrictedMobile.goto(`${baseUrl}?long_names&finance`, { waitUntil: "domcontentloaded" });
  const longDialog = await openMore(restrictedMobile);
  await longDialog.getByRole("button", { name: /^打开京奥电竞跨区域/ }).scrollIntoViewIfNeeded();
  await noOverflow(restrictedMobile, "mobile long names");
  assert.equal(await longDialog.locator(".workspaceMobileEntities").evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, "Long company names must fit the mobile account list");
  await longDialog.getByRole("button", { name: /^打开京奥电竞跨区域/ }).click();
  await lastAction(restrictedMobile, "entity:entity-jingao");
  await dialogClosed(restrictedMobile);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: "passed", checks: "real grouped navigation, authorized modules only, financial account callbacks and collapse, review badge and outbound state, desktop/rail/tablet geometry, low-height independent scrolling, long names, 4 phone portrait/landscape sizes, 44px touch targets, mobile dialog focus trap/Escape/backdrop/restore, account actions and resize recovery", screenshots }));
} finally {
  await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
  fs.rmSync(outDir, { recursive: true, force: true });
}
