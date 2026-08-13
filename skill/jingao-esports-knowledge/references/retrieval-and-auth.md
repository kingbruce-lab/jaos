# 检索、查询 API 与飞书鉴权

## RAG decision

Use RAG for unstructured project documents, narrative experience, similar-case discovery, and asset retrieval. Do not use vector similarity as the source of truth for current company facts, permissions, versions, exact names, dates, results, or numeric fields.

For the initial five-user NAS deployment, use PostgreSQL with full-text search and pgvector before introducing a separate vector database. Split services later only when corpus size, concurrency, or operations justify it.

## Retrieval layers

Apply these layers in order:

0. **Authorization and source-integrity filter**: derive allowed departments,
   projects, confidentiality levels, and document scopes from the verified
   identity, and exclude sources that are missing or fail their registered
   SHA-256 check, before any retrieval.
1. **Canonical/structured retrieval**: SQL or keyed lookup for current facts, effective dates, versions, project records, approved results, and maintained artifacts.
2. **Lexical retrieval**: full-text/BM25-style search for exact project names, clients, people, acronyms, filenames, and quoted phrases.
3. **Semantic retrieval**: vector search for related cases, similar needs, lessons, reusable modules, and visually described assets.
4. **Fusion**: combine lexical and semantic candidates with RRF and metadata.
   The first release does not use a separate Rerank service.
5. **Context assembly**: deduplicate, preserve page boundaries, respect token budget, and attach citations.
6. **Answer generation**: generate only from authorized context and return `资料中未找到` when evidence is insufficient.

The first release uses `grok-4.5` as the primary evidence-answer model and
falls back once to `deepseek-v4-flash`. Every factual sentence must carry a
valid `[S#]` citation. Invalid or unavailable generation degrades to the local
retrieval answer without losing citations.

L4 never leaves the NAS. L3 is local by default and can be sent only when the
founder has enabled the separate L3 generation switch and the verified caller
is the founder. If a result set mixes outbound-eligible evidence with blocked
L3/L4 evidence, keep the whole question local rather than sending a partial
context that could reveal the restricted query meaning.

## Modes

- `exact`: canonical + structured + lexical. Use for company introductions, numbers, dates, people, partners, qualifications, contacts, and current status.
- `semantic`: semantic retrieval only after authorization. Use for exploratory discovery, never final current facts.
- `hybrid`: lexical + semantic + metadata reranking. Default for historical cases, lessons, and proposal research.
- `auto`: server chooses based on query classification and returns the chosen mode.

## Skill and query API

The Skill contains company workflows, prompt rules, output standards, and brand assets. It must not contain database credentials or implement authorization.

The internal query API performs identity verification, authorization, deterministic lookup, RAG retrieval, citation packaging, audit logging, and rate limiting.

Recommended endpoints:

- `GET /v1/status`
- `GET /v1/categories` (active server-managed taxonomy for employees)
- `POST /v1/search`
- `POST /v1/writing/draft` (free-form evidence-grounded editable draft)
- `POST /v1/uploads` (employee upload to the review inbox)
- `GET /v1/projects`
- `GET /v1/projects/{project_id}`
- `GET /v1/documents/{document_id}`
- `POST /v1/proposals/draft`
- `POST /v1/proposals/pptx`
- `POST /v1/evolution/digest`（创始人/资料管理员；本地确定性变化候选，不自动发布）
- `GET/POST /v1/evolution/artifacts`（维护资料清单/创始人登记）
- `GET /v1/evolution/baseline-documents`（可登记的已发布定稿）
- `POST /v1/evolution/artifacts/{id}/runs`（持久复核批次，定时任务亦调用）
- `GET /v1/evolution/runs/{id}`（候选、审批状态与变更计划）
- `POST /v1/evolution/candidates/{id}/decision`（仅创始人，独立审批/披露许可）
- `POST /v1/evolution/runs/{id}/change-plan`（仅创始人，确定性计划，不发布）
- `POST /v1/evolution/runs/{id}/close`（仅创始人；记录复核但不推进截止日）
- `POST /v1/evolution/artifacts/{id}/baseline`（仅创始人；只接受已发布的直接后继版本）
- `GET /v1/review/queue`（创始人/资料管理员，按密级前置过滤）
- `POST /v1/review/inbox/scan`（创始人/资料管理员，仅返回数量汇总）
- `GET /v1/review/inbox/issues`（仅创始人，返回相对路径）
- `POST /v1/review/{document_id}/proposal`（提交建议，不修改资料）
- `POST /v1/review/{document_id}/apply`（仅创始人，明确确认）
- `POST /v1/review/{document_id}/reject`（仅创始人，原资料不变）
- `POST /v1/review/{document_id}/publish`（仅创始人，独立确认；精确替代当前版本）
- `GET /v1/evaluations/latest`（创始人/资料管理员）
- `POST /v1/evaluations/run`（创始人/资料管理员）
- `POST /v1/evaluations/concurrency`（创始人/资料管理员）
- `POST /v1/operations/reconcile-sources`（创始人/资料管理员，只返回数量与状态）
- `GET /v1/me`

The evaluation API targets 150 technical probes: up to 120 page-citation
probes generated only from unique, available source chunks, plus 15 refusal
and 15 permission-isolation probes. A small or duplicate corpus can produce
fewer than 120 valid citation probes; report the shortfall instead of creating
fake business facts or duplicating files. Probe queries are not persisted.
Treat this as a technical baseline only. The separate 150-question business
gold set must be approved by business owners before it is counted or used for
company-fact acceptance.

The first-release search response includes:

`query_id`, `retrieval_mode`, `retrieval_degraded`, `scope`, `scope_reason`,
`answer`, `results`, `denied_count`, and `unavailable_count`.

Each result includes source IDs, version, page, status, effective dates, authority, project, department scope, confidentiality, excerpt, and score breakdown.

Project detail includes `has_closing_report` and `closing_report_reminder` for
project-history review.

The API must filter before vector search. Post-filtering retrieved unauthorized candidates is insufficient because it can leak counts, similarity, metadata, or cached content.

The review API uses a staged-write contract. Proposal submission records
suggested metadata only. Founder apply records the decision and updates
metadata, but must preserve `knowledge_status=candidate`. It never promotes a
document to current knowledge.

The publication endpoint is a separate write contract. It accepts only an
eligible final candidate and requires the exact server-disclosed set of
current-version document IDs that will be superseded. If that set changes,
the server rejects the request so the founder can refresh and confirm again.

## Feishu identity

The five-user trial uses local application accounts and short-lived bearer
sessions. Feishu OAuth and organization synchronization remain the planned
upgrade when the user count exceeds 20 or multiple departments are onboarded.

When that trigger is reached, create a Feishu enterprise custom app and use
Feishu login/SSO to identify the user and synchronize the permitted
organization structure.

Store a stable mapping:

`feishu_user_id → employee_id → departments → roles → project_groups → confidentiality_ceiling → status`.

Prefer a tenant-level stable `user_id` for internal cross-application identity mapping when the required scope is approved. Keep `open_id` for app-specific interactions.

The application:

1. redirects the employee to Feishu authorization;
2. exchanges the authorization result on the server;
3. obtains verified user identity;
4. loads department and role mappings;
5. issues a short-lived internal session;
6. sends the session to the query API;
7. refreshes or revokes access when Feishu membership changes.

Never place the Feishu app secret, access token, or NAS credential in the Skill.

## Authorization model

Combine RBAC and ABAC:

- RBAC: founder, knowledge administrator, department owner, planner, executor, employee.
- ABAC: department, project membership, document role, confidentiality, current/history scope, disclosure permission, and employment status.

Effective permission is the intersection of:

`user permission ∩ department permission ∩ project permission ∩ document ACL ∩ confidentiality policy`.

Administrators may manage indexes without automatically gaining permission to read all restricted content. Log searches, opened sources, exports, and generated artifacts.

## Codex integration

For early development, the Skill may call the query API with a short-lived local session token.

For production, package the Skill with an internal MCP server or trusted connector:

- MCP handles Feishu sign-in and token refresh.
- MCP exposes typed tools such as `search_knowledge`, `get_current_topic`, `get_project`, `search_assets`, and `create_evolution_plan`.
- The Skill decides which tool and workflow to use.
- The API remains the final enforcement point.

This separation allows the API, retrieval model, and database implementation to evolve without changing employee prompts or leaking credentials into Codex.
