# 业务金标题库

技术评测会自动生成 150 个探针，但它只能验证检索、页码引用、拒答和权限隔离，不能判断公司的真实业务事实。

推荐由业务负责人在 Web“系统状态 → 业务金标题库”中录入和审核。系统把题目保存为运行数据目录中的：

`evaluations/business_questions.jsonl`

NAS 默认完整路径为：

`/data/evaluations/business_questions.jsonl`

每行一个 JSON 对象。导入接口始终写入 `approved: false`；同 ID 题目被修改时会撤销旧批准。只有创始人在独立批准步骤中确认的题目才会变为 `approved: true` 并计入 150 题金标。

支持三种预期：

- 指定引用：`expected.document_id`，可选 `expected.page`。
- 应拒答：`expected.expect_refusal: true`。
- 权限无泄露：`expected.expect_no_leak: true`，并设置低密级 `actor`。

不要把密码、模型密钥、合同正文或个人隐私写入题库。题目可以包含真实业务问题，预期答案只保存文档 ID 和页码，不复制原文。

从 `business_questions.example.jsonl` 复制后填写；所有待确认示例均为 `approved: false`，不会进入验收结果。

每日备份会同时复制整个 `evaluations` 目录，业务题库、技术评测和并发报告都包含在备份清单及哈希校验中。
