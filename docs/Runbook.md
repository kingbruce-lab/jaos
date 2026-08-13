# 京奥智库 Runbook（首版）

适用范围：本地测试版与飞牛 NAS Docker Compose 首版。  
原则：先恢复到隔离环境并验收，再切换；任何恢复操作都不得直接覆盖唯一在用副本。

首次在 NAS 上线前，先按 `docs/NAS首次上线.md` 填写未提交的 `.env`，然后执行：

```bash
sh scripts/nas-preflight.sh
```

预检有“失败”项时不得部署；只有“提醒”项时可进入 5 人试点，但不能视为正式发布通过。

### 临时 SSH 维护授权

创始人已授权：本项目所需的临时 SSH 维护访问无需逐次确认。维护人员仍必须
执行完整闭环：临时开启 SSH → 使用独立临时公钥 → 完成维护与验证 →
移除公钥及本机临时凭据 → 关闭 SSH → 复核 22 端口关闭且 Web/监控正常。

该授权只覆盖技术维护，不包含导入真实资料、修改真实员工权限、把候选资料
发布为 `current` 或开启任何云端出网开关。

## 1. 日常状态检查

批量图片首次入库时，OCR 会在 `ingest` 容器后台持续执行。该容器固定限制为 2 个 CPU 核心，优先保证员工 Web、检索和数据库响应；OCR 队列变慢属于预期，不要为追求速度取消该限制。

本地测试：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
Invoke-RestMethod http://127.0.0.1:8000/readyz
Invoke-RestMethod http://127.0.0.1:8000/monitorz
Invoke-WebRequest -UseBasicParsing http://localhost:3000/
cd agent
.\.venv\Scripts\python.exe -m app.cli status
```

NAS：

```sh
sudo sh /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh status
sudo sh /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh logs
```

正常标准：

- Web 与 Agent 均返回 200；
- 数据库健康；
- 磁盘使用率低于 80%；
- 最近 24 小时内存在带 `COMPLETE` 标记且校验通过的备份；
- 搜索引用可以打开原页。

当前内部入口：

```text
http://jadj-nas.local:3000/
```

当前 DHCP 地址是 `192.168.2.53`，只作故障排查使用，不应写死到员工收藏。

### 公网 FRP 入口

NAS 已安装官方 FRP Client `v0.69.0`，由 `jingao-frpc.service` 开机自启并在
异常退出后自动重连：

```text
程序：/vol1/@team/京奥智库/00_部署/frpc/frpc
配置：/vol1/@team/京奥智库/00_部署/frpc/frpc.toml
日志：/var/log/frpc.log
```

配置文件权限必须保持为仅 root 可读，认证令牌不得写入源码、部署包或运维文档。
客户端代理类型必须是 `http`，目标为 NAS 本机 Web `127.0.0.1:3000`；
`customDomains` 不能与 `tcp` 类型混用。

Web 容器必须配置：

```text
JINGAO_WEB_HOSTS=localhost,127.0.0.1,web,jadj-nas.local,192.168.2.53,knowledge.jingao.club
JINGAO_WEB_MAX_REQUEST_BODY_BYTES=2147483648
```

其中 `web` 仅供 Docker 内部的 Agent 验收探针和 Uptime Kuma 使用。增加公网
域名或调整 NAS 地址时必须同步更新白名单；不得用通配符替代。合法 Host 返回
200，未登记 Host 应返回 421，超出 2 GiB 的请求应返回 413。公网 Nginx
同时配置 `client_max_body_size 2048m`、`client_body_timeout 1800s` 和
`proxy_*_timeout 1800s`，否则大文件会在到达 Web 或 Agent 前被中断。

检查：

```sh
sudo systemctl status jingao-frpc.service --no-pager
sudo tail -n 50 /var/log/frpc.log
```

生产入口应为：

```text
https://knowledge.jingao.club/
```

服务器侧只需：

1. 云安全组与主机防火墙允许 NAS 公网出口访问 FRP 控制端口；
2. 现有 HTTPS 反向代理把 `knowledge.jingao.club` 转发到
   `127.0.0.1:8000`（FRPS `vhostHTTPPort`）；
3. 不向公网直接开放 8000，不让员工通过明文 HTTP 登录；
4. 部署完成后轮换在调试期间使用过的 FRP 令牌。

2026-07-28 复核记录：域名 A 记录已指向公网服务器；NAS 可访问该服务器
22/80/443，但 7001/8000 超时；NAS `OUTPUT` 策略为放行，当前公网出口为
`106.37.113.25`。这表示阻塞点在公网服务器安全组、主机防火墙或上游访问
白名单，不在 FRPC、Docker 或 NAS 本机防火墙。放行 7001 后，已经启用的
服务会自动重连。

2026-08-01 进一步复核：NAS 当前公网出口已变为 `1.202.100.44`，与维护电脑
的公网出口不同；NAS 可以连接 `portquiz.net:7001`，但连接
`82.156.239.212:7001` 仍超时。因此 NAS 和路由器并未普遍封禁出站 7001，
阻塞点可收敛到公网服务器对 NAS 新出口的安全组、主机防火墙、拒绝列表或
上游源地址过滤。应同时检查并放行：

```text
来源：1.202.100.44/32
协议：TCP
目标端口：7001
```

不要为了排障长期把 7001 对 `0.0.0.0/0` 开放。NAS 出口变化后需更新 `/32`
规则；若运营商地址频繁变化，应把 FRP 控制连接迁到有 TLS 保护的 443 入口或
采用其他稳定的私网接入，不维护宽泛白名单。当前维护电脑可直接连接公网 8000，
说明该端口存在公网入口；HTTPS 反向代理完成后必须删除安全组的 8000 公网入站
规则，只允许服务器本机反向代理访问 `127.0.0.1:8000`。

### 原件完整性核验

NAS 的 `reconcile` 容器默认每 86400 秒只读核验全部已登记原件。它比较登记时的内容哈希、文件大小与当前文件；文件在知识根目录内移动或改名后，会按 SHA-256 自动重新绑定引用链，不修改、移动或删除 NAS 文件。

查看自动核验日志：

```sh
docker compose logs --tail 100 reconcile
```

手工触发：

```sh
docker compose exec agent \
  python -m app.cli reconcile-sources --path /knowledge
```

也可由创始人或资料管理员在 Web“系统状态”点击“核验原件”。核验结果只返回数量与状态，不向普通员工暴露路径。

- `verified`：路径、大小和 SHA-256 一致，可检索、预览、派生和发布。
- `missing`：原路径不存在且知识根目录内未找到同哈希文件；立即退出正常使用。
- `mismatch`：路径仍存在但内容哈希变化；视为另一份文件，不沿用旧引用。
- `failed`：权限或读取错误；保持隔离，排除存储和 ACL 问题后重试。

恢复原件时应放回完全相同的文件，或把同 SHA-256 文件放入知识根目录后重新核验。不得用“看起来相似”的文件冒充原件，也不得因重新绑定而自动确认元数据或晋升 `current`。

接口分工：

- `/healthz`：只证明 Agent 进程在线；
- `/readyz`：数据库或存储出现严重故障时返回 503，供容器健康检查；
- `/monitorz`：任何“需关注”或“严重”状态都返回 503，供 Uptime Kuma 等内网监控使用；
- Web 端“系统状态”：仅创始人和资料管理员可见，显示容量、备份时效和处理建议。

公开健康接口只返回组件状态，不返回 NAS 路径、容量数字、模型名或密钥。Compose 已为
Agent 和 Web 配置 30 秒一次的容器健康检查。

### WEB 上传目录与待审核目录扫描

通过京奥智库 WEB 上传的文件直接保存为：

```text
<JINGAO_KNOWLEDGE_PATH>/<资料分类名称>/<L1-L4>/<文件名>
```

每个资料分类固定建立 `L1`、`L2`、`L3`、`L4`、`L5` 五个子目录；新增分类自动建目录，分类改名同步重命名目录并更新数据库原件路径。审核状态保存在数据库中，不再通过 `Web上传/日期/内部分类ID` 文件夹表达。

Web「资料上传」支持两种方式：少量文件可以直接多选；照片、视频等批量素材可以选择一个已经命名的文件夹。文件夹模式最多接收 500 份受支持文件，外层文件夹名作为项目/批次名称，照片和视频可保留相机原始文件名。NAS 按 `<资料分类>/<密级>/<文件夹名>/<原子目录>/<原文件名>` 保存，数据库标题显示为 `<文件夹名> / <原文件名>`，因此无需逐个重命名素材。完全相同的文件仍按 SHA-256 自动过滤。

`99_AI入库待审核` 只用于员工通过 SMB 批量放入、尚未在 WEB 中选择分类和密级的历史/散装资料。NAS 的 `ingest` 容器默认每 900 秒只读扫描：

```text
<JINGAO_KNOWLEDGE_PATH>/99_AI入库待审核
```

文件修改时间至少过去 120 秒才会读取，避免把 SMB 尚未上传完成的文件误当成完整资料。支持 PDF、PPTX、DOC/DOCM/DOCX、XLS/XLSX/XLSM、TXT/Markdown、PNG/JPG/JPEG/WebP、常用音视频，以及 AI 设计源文件、ZIP 压缩包和 `.mm` 思维导图；按 SHA-256 去重。Office、PDF、TXT/Markdown 登记为 `candidate` 并进入审核；图片、音视频、AI、ZIP 和 `.mm` 素材自动登记为 `approved` 历史资产，不进入审核队列，也不会自动成为 `current`。fnOS 生成的 `.~#数字` 上传中间文件会被跳过。旧版 DOC/XLS 与 DOCM 通过 NAS 本地 LibreOffice 转换后抽取，不修改原件，也不执行宏；AI 和 ZIP 只登记素材元数据并保留原件，系统绝不自动解包或执行其中内容。扫描阶段只做快速登记，图片 OCR 转入后台派生队列，批量照片不会阻塞记录和问题清单刷新。每次扫描后会自动执行一次仅针对新文件的派生处理：PDF 逐页检查文字层，只对低文字页运行本地 OCR；图片在后台 OCR；DOC/DOCM/DOCX/PPTX 生成引用版 PDF。失败任务不在每个周期反复执行，管理员排查后可手工重试。

查看自动扫描日志：

```sh
docker compose logs --tail 100 ingest
```

手工扫描：

```sh
docker compose exec agent python -m app.cli scan-inbox
```

也可以由创始人或资料管理员在 Web「入库审核」点击“扫描待审核目录”。接口只返回数量，不向资料管理员返回未分类文件名；未分类问题文件名仅创始人可见。

### 审核资料

图片、视频、音频、AI、ZIP 和 `.mm` 等素材无需审核，上传或扫描完成后自动入库。以下步骤只针对 Office、PDF、TXT/Markdown 内容文档：

1. 在 Web 进入「入库审核」。
2. 点击“预览内容”，确认文件正文、原页或图片无误。
3. 元数据正确时直接点击“确认入库”；L1、L2、L3 可勾选后批量确认，前端会按每批最多 50 份自动拆分提交，员工只需点击一次；后端兼容旧页面最多 500 份的一次性请求，网络重试或重复点击按幂等成功处理且不重复写审核日志；L4 必须逐份确认。
4. 元数据不正确时点击“修改信息”，保存后再点击“确认入库”，修改会在确认时一并采用。
5. 原件失联、哈希变化、解析失败或没有可预览内容时，系统禁止确认。将同一原件重新上传到待审核目录，重新扫描后再处理。

确认后的普通资料进入“已确认历史知识”，员工可在权限范围内检索。候选资料在确认前不参与员工检索。公司介绍等代表“当前/最新”口径的资料，确认入库后仍由创始人单独执行“发布为当前版本”。

扫描器不会移动、删除或覆盖 NAS 文件。出现以下情况时不会入库：

- 文件仍在上传或 120 秒静置期未满；
- Office 临时文件、下载临时文件；
- 符号链接或路径越界；
- 单文件超过 2GB；
- 不支持的类型；
- 解析器失败。

问题修复或文件移除后，下次扫描自动把问题标记为已解决。普通资料由创始人或资料管理员一键执行 `candidate → approved`；公司介绍等当前口径再由创始人执行 `approved → current`。

### 发布当前版本

Web「入库审核」仅在以下条件全部满足时向创始人显示可用的发布表单：

1. 没有待确认的元数据建议，且最近的建议已经由创始人确认应用；
2. 项目归属已确认；
3. 资料已标记为定稿；
4. NAS 源文件仍然在线；
5. 非素材类文档至少有一个可引用内容块，页数记录大于零。

发布面板会列出同一资料系列当前有效的全部版本。公司介绍按“公司资料业务线 + 公司介绍角色”识别系列；其他文档按项目名称、客户、业务线和文档角色识别；素材还要求标题一致。创始人输入“确认发布为当前版本”后，系统将候选资料设为 `current`，记录 `valid_from`，并把面板列出的旧版本设为 `superseded`、记录 `valid_to`。旧版本不会删除。

发布接口要求客户端回传完整的旧版本 ID 集合。若另一名管理员在页面打开后改变了版本状态，服务器返回冲突并拒绝发布；刷新审核队列、重新核对后才能再次确认。发布审计动作名为 `knowledge_published`，记录新旧文档 ID 与生效时间，不保存确认短语或发布说明正文。

### 告警接入

Uptime Kuma 只在 NAS 局域网 `3001` 端口提供管理界面，数据保存在独立
Docker 卷。至少新增两个 HTTP 检查：

```text
JAOS 运行状态：http://agent:8000/monitorz
JAOS 员工入口：http://web:3000/
```

第一个检查返回 200 表示数据库、存储、内存、主备份、第二物理备份和原件核验全部正常，返回 503
表示需要查看 Web 端“系统状态”；第二个检查确认员工页面可打开。飞书或
微信告警接收目标属于外部发送配置，待创始人确认具体群或负责人后再启用。
不得把 Docker Socket 挂进 Uptime Kuma。

## 2. 重启

本地测试：

```powershell
.\scripts\start-agent.ps1
.\scripts\start-web.ps1
```

NAS：

```sh
cd /vol1/@team/京奥智库/00_部署/jingao-runtime
docker compose --env-file .env -f docker-compose.yml \
  restart agent web ingest reconcile
sudo sh /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh status
```

数据库正常时不要随意重启 `db`。如必须重启：

```sh
docker compose restart db
docker compose ps
```

等待数据库健康后再检查 Agent。

## 3. 立即备份

### 本地 SQLite

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup-now.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-latest-backup.ps1
```

备份包包含：

- SQLite 一致性快照；
- 受控原件副本；
- DOCX/PPTX 引用版 PDF 等派生文件；
- 文件大小及 SHA-256 清单；
- 数据表数量；
- 最后写入的 `COMPLETE` 完成标记。

验证器不会接受无 `COMPLETE` 标记、清单被修改、文件缺失、大小变化或哈希不一致的备份。

### NAS PostgreSQL

`backup` 容器启动后默认等待 120 秒，让扫描和派生服务稳定；随后先执行一次只读原件完整性对账，再创建备份，之后默认每 86400 秒重复“对账 → 备份”。它使用 PostgreSQL 16 的
`pg_dump`，并与原件、派生文件一起生成同样的哈希清单。

手工触发：

```sh
docker exec jingao-copilot-backup-1 \
  python -m app.cli backup --output /backup
```

手工验证：

```sh
docker exec jingao-copilot-backup-1 \
  python -m app.cli verify-backup \
  --path /backup/<备份目录>
```

备份容器必须把 `JINGAO_KNOWLEDGE_PATH` 以只读方式挂载到 `/knowledge`。
验证结果中的 `source_files_missing_at_backup` 必须为 0；只校验
`database.dump` 成功但没有封入可用原件，不算完整备份。

`JINGAO_BACKUP_PATH` 是 NAS 主备份目录。它可以用于误删恢复和版本回退，但当前与生产数据在同一块硬盘时，不算灾难恢复备份。

### 第二物理介质备份

把 `JINGAO_OFFSITE_BACKUP_PATH` 配置为另一块物理硬盘、移动硬盘或异机挂载目录。系统会比较主备份与目标目录的设备号；同一物理设备会被明确拒绝。

插入介质后手工执行：

```sh
sudo /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh offsite-backup
```

同步器只复制带 `COMPLETE` 和密封清单的最新主备份，先写入 `.incomplete-*` 临时目录，完成后原子改名，并使用 JAOS Agent 镜像重新验证数据库包、文件大小和 SHA-256。验证成功后才把“第二物理备份”状态设为正常。

系统每天 03:30（有最多 15 分钟随机延迟）自动尝试同步。以下情况会在“系统状态”和 `/monitorz` 明确告警：

- 尚未配置目标；
- 移动硬盘未插入或挂载；
- 目标与 NAS 主备份处于同一物理设备；
- 目标不可写；
- 复制或哈希校验失败；
- 最近成功同步超过 7 天。

没有第二介质时，告警是预期且真实的安全状态，不得通过指向同盘目录来消除。

## 4. 恢复演练

### 本地 SQLite 隔离演练

不改变当前运行库：

```powershell
cd agent
.\.venv\Scripts\python.exe -m app.cli verify-backup `
  --path .\backups\<备份目录> `
  --restore-check
```

该命令会在临时目录恢复数据库，重新绑定受控原件及派生文件，检查：

- `PRAGMA integrity_check`；
- 项目、文档、分块、向量数量；
- 受控原件 SHA-256；
- 每份可用引用版 PDF 的哈希、页数和可读性；
- 备份内旧登录会话被全部注销，恢复后所有用户必须重新登录。

临时恢复目录在验收后自动删除。

需要保留一个隔离恢复副本时：

```powershell
.\.venv\Scripts\python.exe -m app.cli restore-sqlite `
  --path .\backups\<备份目录> `
  --target C:\jingao-restore-test
```

目标目录必须为空；命令拒绝覆盖已有目录内容。

### NAS PostgreSQL 演练

1. 先验证备份包和 `database.dump`。
2. 新建隔离数据库，例如 `jingao_restore_test`，不要恢复到正在使用的 `jingao`。
3. 使用备份容器中的 PostgreSQL 16 `pg_restore` 恢复到隔离数据库。
4. 启动一个只监听本机临时端口的 Agent，连接隔离数据库。
5. 核对用户、项目、文档和分块数量，验证备份内原件 SHA-256 与引用路径。
6. 清空恢复库的 `session_tokens`，确认恢复后所有用户必须重新登录。
7. 核对权限探测题、搜索引用和原页预览。
8. 演练通过后删除隔离数据库；正式故障时，经创始人确认后才允许切换连接地址。

任何 `--clean`、删除数据库或覆盖当前库的操作都属于破坏性操作，必须在明确确认目标和可恢复备份后执行。

## 5. 索引重建

全文索引随数据库恢复。Embedding 重建：

```powershell
cd agent
.\.venv\Scripts\python.exe -m app.cli embed --force
```

规则：

- L4 永不出网、永不建向量；
- L3 默认不建向量，只有创始人批准后才能打开；
- Embedding 模型名变化时应新建索引并跑评测，不可直接把旧向量当作新模型向量；
- 网关不可用时，搜索自动降级为确定性检索。

### 证据回答

云端生成和 Embedding 使用独立开关。未注入轮换后的正式 Secret 时，保持：

```text
JINGAO_LLM_ENABLED=false
JINGAO_LLM_L3_ENABLED=false
```

开启 `JINGAO_LLM_ENABLED=true` 后，Agent 先把已经完成身份、密级、版本、状态和源文件检查的证据组装为带 `[S1]` 编号的上下文，再调用 Grok 4.5。主模型出现限流、网络故障、响应格式错误或逐句引用校验失败时，只回退一次 DeepSeek；回退仍失败则返回本地确定性检索结果，不阻塞员工。

出网硬边界：

- L4 证据永不发送，也没有开关；
- L3 默认不发送；只有 `JINGAO_LLM_L3_ENABLED=true` 且当前会话为创始人时才允许；
- 如果一次命中混合包含不允许出网的 L3/L4，整次问答保持本地，不能只发送较低密级部分，以免问题文本泄露高密级语义；
- 最多发送 8 条证据、每条最多 1200 字符、总上下文默认最多 10000 字符；
- 审计只记录问题哈希、出网文档 ID、模型、回退状态和字符数，不记录原问题、证据正文或确认短语。

## 6. 自动化回归验收

旧“技术评测/知识进化”页面已下线，不再作为生产入口。每次发布必须在开发机运行当前正式能力的完整测试：

```powershell
pnpm test
cd agent
.\.venv\Scripts\python.exe -m pytest -q
```

测试不得通过忽略失败、保留已移除接口的过期用例或复制虚假业务资料来变绿。检索业务质量仍需以真实问题和人工引用核对验收；自动化测试只证明代码、权限和数据链路未回归。

## 7. 版本发布、升级与回滚

升级前：

1. 立即备份；
2. 运行完整校验和隔离恢复演练；
3. 执行 `manage.sh release` 记录当前版本、源码指针和最近发布历史；
4. 运行自动化测试。

NAS 升级：

```sh
sudo sh /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh build
sudo sh /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh build-status
sudo sh /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh start
sudo sh /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh status
```

出现阻断回归时：

```sh
sudo sh /vol1/@team/京奥智库/00_部署/jingao-runtime/manage.sh rollback
```

详细规则、发布包校验和回滚边界见 `docs/发布与回滚.md`。

升级后检查：

- 登录；
- 当前事实查询拒答；
- 历史案例检索；
- L2 账号无法看到 L3；
- 引用原页；
- 备份容器日志。

## 8. 常见故障

### 原件失联

- 系统自动把相关分块排除出搜索；
- 普通员工看不到失联数量；
- 管理员审核队列显示问题；
- 恢复同 SHA-256 原件后重新入库，不要用相似文件冒充。

### 网关不可用

- 确定性检索继续工作；
- 语义检索自动降级；
- 证据回答先尝试一次 DeepSeek 回退，仍失败则显示本地证据结果；
- 不反复重试造成费用或阻塞；
- 检查网关额度、模型目录和 Secret，不在日志中输出 Key。

### 磁盘接近 80%

- 暂停大批量解析；
- 检查备份是否误放在数据库同一卷；
- 清理必须先生成清单，不删除原件、唯一备份或未经批准的历史记录。

### 数据库异常

- 停止写入；
- 保留故障现场；
- 验证最近两个备份；
- 先隔离恢复，验收后再决定是否切换。

## 9. 演练记录

每次记录：

- 日期、执行人；
- 备份目录与 manifest SHA-256；
- 数据库数量；
- 受控原件校验数量；
- 引用版 PDF 校验数量；
- 恢复耗时；
- 是否通过及异常。

至少每季度执行一次完整恢复演练。
