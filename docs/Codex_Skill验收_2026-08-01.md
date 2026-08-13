# 京奥电竞知识库 Codex Skill 验收（2026-08-01）

## 结论

`jingao-esports-knowledge` v1.12 已更新并安装到本机 Codex。Skill 只通过 NAS 鉴权 API 使用知识，不直读数据库或 NAS 路径，也不保存、打印访问令牌。

## 已覆盖能力

- 搜索当前公司事实、历史项目和引用原页；
- 查看、生成草稿和人工确认项目知识卡；
- 生成带来源备注的电竞培训提案 PPT 初稿；
- 运行一次性 `evolution-digest` 临时变化检查；
- `evolution-artifacts`：查看有权限的维护资料；
- `evolution-baselines`：列出可登记的当前、定稿、原件完整基线；
- `evolution-register`：仅创始人显式请求时登记维护资料；
- `evolution-run` / `evolution-review`：启动并查看持久化复核；
- `evolution-candidate-decide`：分别处理内部纳入、外宣披露和拒绝；
- `evolution-plan`：在全部候选处理后生成确定性变更计划；
- `evolution-close`：完成复核但不推进资料截止线；
- `evolution-baseline`：新文档已经发布为当前版后，显式更新维护基线。

Skill 明确区分候选接受、对外披露、变更计划、复核完成、文档发布和基线更新；任何一步都不会推断下一步已获批准。

## 精确确认短语

- 项目知识卡：`确认知识卡`；
- 对外候选：`确认纳入并允许对外披露`；
- 内部候选：`确认纳入变更计划`；
- 拒绝候选：`确认不纳入`；
- 生成变更计划：`确认生成变更计划`；
- 完成本次复核：`确认完成本次复核`；
- 更新维护资料基线：`确认更新维护资料基线`。

## 验收证据

- Skill Creator `quick_validate.py`：源码与安装副本均通过；
- Python 编译与 Skill 鉴权 API 模拟测试：通过；
- Agent 全量自动化：76/76 通过；
- 源码 Skill 与本机安装副本 13 个文件哈希一致；
- 分发 ZIP 共 13 个文件，无缓存文件，无已知密码、令牌或 API Key 命中；
- 分发包：`jingao-esports-knowledge-v1.12.zip`；
- ZIP SHA-256：`F5308B2A8E8FC1E7DD85162520C55A659C9FD7E47D77F8BAC2A2C0D37B01D028`。
