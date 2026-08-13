# 京奥 AI 智能运营系统（JAOS）

JAOS 是京奥电竞部署在飞牛 NAS 上的内部运营系统。系统已由 10 余名员工试用，当前覆盖组织知识、资料治理、智能创作、合同档案、财务分析和项目管理，不再只是“京奥智库”。

当前正式版本见 [`VERSION`](VERSION)，版本变更见 [`CHANGELOG.md`](CHANGELOG.md)。

## 已上线能力

- 本地账号、组织角色、L1–L5 密级、会话和全链路审计；
- NAS 文件/文件夹上传、自动扫描、SHA-256 精确去重、Office/PDF 解析、扫描 PDF 本地 OCR、审核/拒绝/批量处理；
- 确定性全文检索与可选语义检索、页码引用、权限过滤、原页预览；
- 基于授权资料的智能创作，最近一次自动保存、每用户 5 条手工稿、Markdown 下载；
- 行政/人事/业务/总办合同档案和 L4/L5 权限；
- 三家公司独立财务账套、银行流水确认、周/月/年经营流量、资金健康、异常规则与集团内部划转；
- 项目立项、创始人复核、执行团队、合同状态、预算/税费、现金流、进度、结案、回款和归档；
- 手机端底部导航、更多菜单、表格卡片化及安全区适配；
- 每日 PostgreSQL + 原件封存备份、原件完整性核验、第二物理介质同步器和显式告警；
- 版本化发布包、SHA-256 校验、当前/上一版本指针和一键回滚。

## 明确未启用

- “知识进化”和旧技术评测页面已从正式产品移除；
- MCP、飞书 OAuth/组织同步、飞书 OA 审批自动比对仍在后续范围；
- L4/L5 内容永不发送到云端模型；L3 默认不出网，必须按次授权。

## 工程结构

```text
app/                 Web 前端与 Agent 反向代理
agent/app/           FastAPI 服务、权限、解析、检索、财务与项目逻辑
agent/tests/         当前正式能力的自动化测试
docs/                Runbook、发布回滚和治理规则
scripts/             构建、部署、备份、验收与运维脚本
skill/               京奥内部知识 Codex Skill
compose.yaml         NAS Docker Compose 生产栈
VERSION              当前正式版本号
```

## 本地开发

Agent：

```powershell
cd agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:JINGAO_DEV_MODE="true"
$env:JINGAO_BOOTSTRAP_PASSWORD="仅用于本机的测试密码"
.\.venv\Scripts\python.exe -m app.cli init
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Web：

```powershell
pnpm install
$env:JINGAO_AGENT_URL="http://127.0.0.1:8000"
pnpm dev
```

## 全量验证

```powershell
pnpm test
cd agent
.\.venv\Scripts\python.exe -m pytest -q
```

正式发布不得只验证“页面能打开”；前端生产构建与 Agent 全量测试必须同时为绿色。

## 打包、发布和回滚

```powershell
.\scripts\package-nas.ps1
```

发布包包含版本、Git 提交、文件清单和 SHA-256，不包含 `.env`、密钥、数据库或业务资料。NAS 发布与一键回滚流程见 [`docs/发布与回滚.md`](docs/发布与回滚.md)。

## 备份边界

`JINGAO_BACKUP_PATH` 是 NAS 主备份，若它与生产数据在同一块硬盘上，只能防误删和逻辑故障，不能防硬盘损坏。

第二备份必须把 `JINGAO_OFFSITE_BACKUP_PATH` 指向另一块物理硬盘、移动硬盘或异机挂载。未配置、未插入、同盘、过期或校验失败时，“系统状态”会明确告警，系统不会把同盘目录伪装成第二备份。

插入介质后执行：

```sh
sudo /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh offsite-backup
```

完整日常运维见 [`docs/Runbook.md`](docs/Runbook.md)。
