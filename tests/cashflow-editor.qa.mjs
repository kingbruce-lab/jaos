import assert from "node:assert/strict";
import { build, preview } from "vite";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "jaos-cashflow-editor-"));
await build({ configFile: false, plugins: [react()], build: { outDir, rollupOptions: { input: "tests/cashflow-editor-ui.html" } } });
const server = await preview({ configFile: false, build: { outDir }, preview: { host: "127.0.0.1", port: 4181, strictPort: true } });
const browser = await chromium.launch({ channel: "msedge", headless: true });
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    await page.goto("http://127.0.0.1:4181/tests/cashflow-editor-ui.html");
    await page.getByRole("button", { name: "修改计划" }).click();
    await page.getByLabel("计划金额（元）").fill("90000");
    await page.getByRole("button", { name: "保存修改" }).click();
    await page.getByRole("alert").waitFor();
    assert.equal(await page.getByTestId("amount").textContent(), "480000");
    await page.getByLabel("计划金额（元）").fill("460000");
    await page.getByRole("button", { name: "保存修改" }).click();
    await page.getByRole("status").filter({ hasText: "计划已更新" }).waitFor();
    assert.equal(await page.getByTestId("amount").textContent(), "460000");
    await page.getByRole("button", { name: "修改计划" }).click();
    assert.equal(await page.getByLabel("计划金额（元）").inputValue(), "460000");
    await page.getByLabel("计划金额（元）").fill("450000");
    await page.getByRole("button", { name: "取消", exact: true }).click();
    assert.equal(await page.getByTestId("amount").textContent(), "460000");
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.close();
  }
  console.log("Cashflow editor desktop/mobile: save, error, reopen, cancel PASS");
} finally {
  await browser.close();
  await server.httpServer.close();
}
