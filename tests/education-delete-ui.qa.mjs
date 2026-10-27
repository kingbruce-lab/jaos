import assert from "node:assert/strict";
import { build, preview } from "vite";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "jaos-education-delete-"));
await build({configFile:false,plugins:[react()],build:{outDir,rollupOptions:{input:"tests/education-ui.html"}}});
const server = await preview({configFile:false,build:{outDir},preview:{host:"127.0.0.1",port:4179,strictPort:true}});
const browser = await chromium.launch({headless:true,...(process.platform==="win32" ? {channel:"msedge"} : {executablePath:process.env.JAOS_BROWSER_EXECUTABLE || "/usr/bin/chromium"})});
try {
  for (const width of [1440,390]) {
    const page = await browser.newPage({viewport:{width,height:900}});
    const errors=[];
    page.on("pageerror",error=>errors.push(error.message));
    const open = async query => {
      await page.goto("http://127.0.0.1:4179/tests/education-ui.html"+query);
      await page.getByRole("button",{name:/2026年10月托管教培班/}).click();
    };
    await open("");
    await page.locator(".educationDetail").waitFor();
    assert.equal(await page.locator(".educationCohortDelete").count(),0);
    await open("?delegated_delete=1");
    const deletion=page.locator(".educationCohortDelete");
    await deletion.getByText("已授权 · 删除本人班期",{exact:true}).click();
    await deletion.getByLabel("当前账号登录密码",{exact:true}).fill("fixture-own-login");
    assert.equal(await deletion.getByRole("button",{name:"设置删除密码",exact:true}).count(),0);
    await deletion.getByLabel("确认班期名称",{exact:true}).fill("2026年10月托管教培班");
    await deletion.getByLabel("删除原因",{exact:true}).fill("本人重复创建的测试班期");
    page.once("dialog",dialog=>dialog.dismiss());
    await deletion.getByRole("button",{name:"验证密码并删除班期",exact:true}).click();
    assert.equal(await page.locator(".educationCohortList button").count(),1);
    page.once("dialog",dialog=>dialog.accept());
    await deletion.getByRole("button",{name:"验证密码并删除班期",exact:true}).click();
    await page.getByText("班期已删除，已从日常页面及教培汇总移除；历史资料保留供追溯。",{exact:true}).waitFor();
    assert.equal(await page.locator(".educationCohortList button").count(),0);
    await open("?founder=1");
    const founderDeletion=page.locator(".educationCohortDelete");
    await founderDeletion.getByText("创始人权限 · 删除班期",{exact:true}).click();
    await founderDeletion.getByRole("button",{name:"设置删除密码",exact:true}).waitFor();
    assert.equal(await founderDeletion.getByText("已授权 · 删除本人班期",{exact:true}).count(),0);
    assert.deepEqual(errors,[]);
    await page.close();
  }
  console.log("PASS: desktop/mobile scoped deletion, cancellation, refresh, ungranted UI hidden, founder flow preserved");
} finally {
  await browser.close();
  await new Promise(resolve=>server.httpServer.close(resolve));
}
