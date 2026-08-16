import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const page = fs.readFileSync(path.join(process.cwd(), "app", "page.tsx"), "utf8");
const styles = fs.readFileSync(path.join(process.cwd(), "app", "globals.css"), "utf8");
const layout = fs.readFileSync(path.join(process.cwd(), "app", "layout.tsx"), "utf8");
const agent = fs.readFileSync(path.join(process.cwd(), "agent", "app", "main.py"), "utf8");
const skill = fs.readFileSync(path.join(process.cwd(), "skill", "jingao-esports-knowledge", "SKILL.md"), "utf8");
const compose = fs.readFileSync(path.join(process.cwd(), "compose.yaml"), "utf8");

test("employee workflow uses dynamic categories and freeform knowledge writing", () => {
  assert.match(page, /v1\/categories/);
  assert.match(page, /v1\/admin\/categories/);
  assert.match(page, /用智库资料写初稿/);
  assert.match(page, /v1\/writing\/draft/);
  assert.match(page, /直接说明你要写什么/);
  assert.doesNotMatch(page, /name: "提案共创"/);
});

test("knowledge writing persists the latest work and up to five saved drafts", () => {
  assert.match(page, /v1\/writing\/drafts/);
  assert.match(page, /v1\/writing\/drafts\/latest/);
  assert.match(page, /最近一次创作已自动保存/);
  assert.match(page, /保存草稿/);
  assert.match(page, /下载 Markdown/);
  assert.match(page, /已达到 5 条保存上限/);
  assert.match(page, /method: "DELETE"/);
  assert.match(page, /safeWritingFilename/);
  assert.match(styles, /\.writingPersistenceBar/);
  assert.match(styles, /\.writingDraftLibrary/);
});

test("mobile shell keeps core work reachable and respects phone safe areas", () => {
  assert.match(page, /mobilePrimaryTabNames:[^=]*= \["工作台", "AI资料检索", "智能创作", "资料上传"\]/);
  assert.match(page, /className="mobileTabbar"/);
  assert.match(page, /className="mobileMenuSheet"/);
  assert.match(page, />更多</);
  assert.match(page, />修改密码</);
  assert.match(page, />退出登录</);
  assert.match(page, /scrollToMobileResult\(searchResultRef\)/);
  assert.match(page, /scrollToMobileResult\(writingResultRef\)/);
  assert.doesNotMatch(page, /current-password" autoFocus/);
  assert.match(layout, /viewportFit: "cover"/);
  assert.match(layout, /interactiveWidget: "resizes-content"/);
  assert.match(styles, /\.mobileTabbar \{/);
  assert.match(styles, /\.mobileMenuSheet \{/);
  assert.match(styles, /env\(safe-area-inset-bottom\)/);
  assert.match(styles, /@media \(max-width: 360px\)/);
  assert.match(styles, /font-size: 16px/);
  assert.match(page, /mobileDataCards financeTransactionCards/);
  assert.match(page, /mobileDataCards pmCashflowCards/);
  assert.match(page, /projectDetailRef\.current\?\.scrollIntoView/);
  assert.match(styles, /\.desktopDataTable \{\s*display: none;/s);
  assert.match(styles, /\.mobileDataCards \{\s*display: grid;/s);
});

test("employee can upload through the knowledge Web app", () => {
  assert.match(page, /name: "资料上传"/);
  assert.match(page, /\/api\/kb\/v1\/uploads/);
  assert.match(page, /multiple/);
});

test("review supports visible L1-L3 batch approval and the approved level names", () => {
  assert.match(page, /batchReviewCandidateIds/);
  assert.match(page, /批量审核 · 共/);
  assert.match(page, /全选待审核/);
  assert.match(page, /BATCH_REVIEW_CHUNK_SIZE = 50/);
  assert.match(page, /requestedIds\.slice\(offset, offset \+ BATCH_REVIEW_CHUNK_SIZE\)/);
  assert.match(page, /apiErrorMessage\(payload, response\.status\)/);
  assert.match(page, /拒绝入库/);
  assert.match(page, /拒绝所选/);
  assert.match(page, /v1\/review\/reject-batch/);
  assert.match(agent, /\/v1\/review\/\{document_id\}\/decline/);
  assert.match(agent, /source_retained/);
  assert.doesNotMatch(page, /payload\?\.detail \|\|/);
  assert.match(page, /L1: "公司公共资料"/);
  assert.match(page, /L2: "业务普通资料"/);
  assert.match(page, /L3: "业务敏感资料"/);
  assert.match(page, /L4: "核心敏感资料"/);
});

test("upload and review controls use readable typography and the sidebar logo is not cropped", () => {
  assert.match(styles, /\.uploadOptions select \{[^}]*font-size: 16px/s);
  assert.match(styles, /\.reviewCardHeader strong \{ font-size: 17px; \}/);
  assert.match(styles, /\.reviewFacts \{[^}]*repeat\(3,/s);
  assert.match(styles, /\.logoFrame img \{[^}]*object-fit: contain/s);
});

test("JAOS brand uses the transparent Jingao mark in a vertical sidebar lockup", () => {
  assert.match(page, /京奥AI智能运营系统/);
  assert.match(page, />JAOS</);
  assert.match(page, /src="\/jingao-mark-transparent\.png"/);
  assert.match(styles, /\.brand \{[^}]*flex-direction: column/s);
  assert.doesNotMatch(styles, /\.logoFrame \{[^}]*background:\s*#fff/s);
});

test("finance purpose corrections require founder review and preserve bank evidence", () => {
  assert.match(page, /v1\/finance\/transactions\/\$\{encodeURIComponent\(transactionId\)\}\/purpose-corrections/);
  assert.match(page, /v1\/finance\/purpose-corrections\/\$\{encodeURIComponent\(correctionId\)\}\/review/);
  assert.match(page, /银行原始附言永久保留/);
  assert.match(page, /提交创始人复核/);
  assert.match(page, /批准并采用/);
  assert.match(page, /拒绝用途修正时必须填写原因/);
  assert.match(styles, /\.financePurposeReviewPanel/);
  assert.match(styles, /\.transactionPurposeWorkflow/);
});

test("finance trend distinguishes net inflow from net outflow using Chinese finance colors", () => {
  assert.match(page, /近 26 周收支与净流入趋势/);
  assert.match(page, /右侧显示当周净流入或净流出，不是收入金额/);
  assert.match(page, /formatMoney\(Math\.abs\(net\)\)/);
  assert.match(styles, /\.trendNetValue\.inflow b \{ color: #c83b45; \}/);
  assert.match(styles, /\.trendNetValue\.outflow b \{ color: #128159; \}/);
});

test("approved documents have local AI confidentiality governance with manual control", () => {
  assert.match(page, /name: "资料治理"/);
  assert.match(page, /v1\/governance\/documents/);
  assert.match(page, /v1\/governance\/ai-classify/);
  assert.match(page, /AI本地初筛，您最终确认/);
  assert.match(page, /L1至L3可批量调整/);
  assert.match(agent, /source": "local_policy_classifier"/);
  assert.match(agent, /L4\/L5只能由创始人逐份调整/);
  assert.match(styles, /\.governanceStats/);
});

test("retired evaluation and evolution features are not published", () => {
  const tabBlock = page.match(/const tabs:[\s\S]*?\n\];/)?.[0] || "";
  assert.doesNotMatch(tabBlock, /知识进化/);
  assert.match(page, /ADVANCED_GOVERNANCE_ENABLED = false/);
  assert.match(agent, /_RETIRED_PRODUCT_API_PREFIXES = \("\/v1\/evaluations", "\/v1\/evolution"\)/);
  assert.doesNotMatch(skill, /evolution-(?:digest|artifacts|run|review|plan|close|baseline)/);
  assert.doesNotMatch(compose, /app\.cli evolution-due/);
});

test("retired project-card workflow is absent and search uses the new name", () => {
  assert.match(page, /AI资料检索/);
  assert.doesNotMatch(page, /项目知识库|AI 问答|知识卡|knowledge-card/);
  assert.doesNotMatch(agent, /\/knowledge-card/);
  assert.doesNotMatch(skill, /project-card|知识卡/);
});
