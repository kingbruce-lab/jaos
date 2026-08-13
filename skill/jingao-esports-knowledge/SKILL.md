---
name: jingao-esports-knowledge
description: Search and use Jingao Esports' internal NAS knowledge base with server-managed categories for current company facts, project history, case studies, source-grounded free-form writing, proposals, reports, course plans, and PPTs. Use when employees ask Codex to learn or review a Jingao project, find reusable experience, compare cases, write materials from authorized internal knowledge, or draft evidence-grounded updates to a company introduction or capability deck.
---

# 京奥电竞知识库

Use the internal knowledge base as the factual source for Jingao-specific work. Never invent company cases, clients, results, budgets, partnerships, or capabilities.

## Start every task

1. Identify the requested domain, audience, deliverable, time period, and confidentiality level.
2. Run `scripts/jingao_knowledge.py status`.
3. Run `scripts/jingao_knowledge.py categories` before applying a category
   filter. Treat returned active categories as the source of truth; the
   examples bundled with this Skill are not a fixed taxonomy.
4. Determine whether the user needs `current` or `history`. Default company facts to `current` and case discovery to `history`.
5. Read `references/retrieval-and-auth.md` when selecting a retrieval mode or handling access.
6. Search before drafting. Use deterministic retrieval for exact/current facts and hybrid retrieval for cases, experience, and assets.
7. Preserve each result's `document_id`, title, version, page, project,
   validity, and source-availability status. Never request or expose a NAS
   absolute path.
8. Distinguish retrieved facts from recommendations and new creative proposals.

If the knowledge service is unavailable, say that internal evidence could not be retrieved. Continue only with generic industry guidance or user-provided materials, clearly labeled as such.

## Choose the workflow

### Learn or review a project

1. Search the project name, client, year, and related domain with history scope.
2. Retrieve proposal, execution, data, closing report, and retrospective when available.
3. Produce: background, client need, solution, execution, results, lessons, reusable modules, and unresolved gaps.
4. Cite every company-specific conclusion with source title, version, and page.

### Write a document with knowledge-base evidence

1. Accept the employee's free-form writing instruction; do not force it into
   a proposal template, slide count, or fixed collaboration workflow.
2. Discover active categories, then use an optional category only when the
   employee requests one or the scope is unambiguous.
3. Call `scripts/jingao_knowledge.py writing "INSTRUCTION"` with the required
   current/history scope. The server retrieves only authorized evidence and
   returns an editable draft plus sources.
4. Preserve `[S#]` citations and the source list while editing. Label new
   recommendations, assumptions, and missing information separately.
5. Respect `generation_mode`. Never send `local_only` evidence to another
   model or gateway to obtain a more polished answer.
6. If no source is returned, state `资料中未找到` and continue only with clearly
   labeled generic guidance or user-provided material.

### Create a solution or proposal

1. Convert the user's brief into objectives, audience, budget, geography, duration, deliverables, and constraints.
2. Retrieve current company facts from canonical knowledge with current scope.
3. Search for 3–5 related historical projects with history scope.
4. Build an evidence table: reusable element, source project, why relevant, required adaptation, freshness, and risk.
5. Draft the new solution. Never copy stale dates, prices, participant counts, partners, or outcomes into the new project.
6. Mark missing business decisions as `待确认`.
7. Include a source appendix.

### Create a PPT

1. Complete the proposal workflow first.
2. Read `references/presentation-workflow.md`.
3. For a fast editable eight-slide training proposal draft, call
   `scripts/jingao_knowledge.py proposal-pptx ...`. The server applies the
   Jingao brand template, authorization-filtered candidate references, and a
   `[Sources]` block in every slide's speaker notes.
4. For a bespoke or externally polished deck, use the installed
   presentation-creation skill after retrieval, then visually verify every
   slide.
5. Use `assets/jingao-logo.jpg` and the brand system in
   `references/brand.md`.
6. Keep unconfirmed facts visibly marked `待确认`; never remove source notes
   before business review.

### Periodic knowledge consolidation

1. Read `references/governance.md` and `references/freshness.md`.
2. Use the authenticated knowledge API's ingestion and status results. Do not
   traverse NAS paths directly from the Skill.
3. Treat directory and filename classification as unconfirmed prefill.
4. Group versions under one project; never treat every exported file as a separate project.
5. Submit metadata as a review proposal; do not write confirmed metadata at
   proposal time.
6. For content documents that require review, require an authorized reviewer
   to confirm ingestion. L1-L3 documents may be batch-confirmed; L4 documents
   must be confirmed individually. Image, video, audio, design-source,
   archive, and mind-map assets are registered as `approved` historical assets
   without entering the review queue.
7. A founder may separately publish an eligible candidate through the
   authenticated publication endpoint. The UI/API must show the complete
   current-version replacement scope, and the founder must enter the exact
   confirmation phrase. Never call this endpoint merely because a user asks
   for "the latest" or because a filename looks newer.
8. Create reusable knowledge blocks only after the final version and outcome
   are confirmed.
9. Send low-confidence classifications and conflicts to human review.
10. Never auto-promote a newer file to canonical merely because its modified time is later.
11. Use only results whose source passed server-side integrity checks. A
    missing, unreadable, or hash-mismatched source is unavailable evidence,
    even if parsed text remains in the database.

## Search commands

```powershell
python scripts/jingao_knowledge.py categories
python scripts/jingao_knowledge.py writing "根据智库资料写一份项目复盘初稿，标注全部来源" --scope history
python scripts/jingao_knowledge.py writing "更新当前公司简介中的核心业务段落" --category company --scope current
python scripts/jingao_knowledge.py search "公司介绍 核心能力" --scope current --retrieval exact --limit 8
python scripts/jingao_knowledge.py search "高校 电竞培训 人才培养" --domain training --scope history --retrieval hybrid --limit 8
python scripts/jingao_knowledge.py project "高校电竞人才培养计划"
python scripts/jingao_knowledge.py document DOC_ID
python scripts/jingao_knowledge.py proposal-pptx --title "高校电竞人才培养项目" --client "某高校" --objective "建立人才培养与实践路径" --audience "高校学生" --duration "6周" --deliverables "课程、实训成果与结案报告" --output "提案初稿.pptx"
```

The client reads:

- `JINGAO_KB_URL`: internal knowledge-service URL.
- `JINGAO_KB_TOKEN`: employee or machine access token.
The Skill never reads the database directly. All retrieval and PPT generation
must pass through the authenticated API so authorization and audit rules remain
effective. Never print tokens or connection secrets.

## References

- Read `references/domains.md` before category-scoped search, writing, upload,
  classification, or comparison. The service response, not the Skill file,
  defines the active taxonomy.
- Read `references/schema.md` when forming structured queries or interpreting results.
- Read `references/governance.md` for ingestion, versioning, summarization, deletion, and human review.
- Read `references/freshness.md` whenever selecting current facts, handling duplicates, or answering an as-of question.
- Read `references/retrieval-and-auth.md` for RAG, exact/semantic/hybrid retrieval, query API contracts, Feishu identity, and department authorization.
- Read `references/presentation-workflow.md` for proposal and PPT outputs.
- Read `references/brand.md` whenever producing a Jingao-branded artifact.

## Safety and quality

- Apply knowledge-service permissions before retrieval; do not work around denied results.
- Respect `generation_mode=local_only` and generation degradation from the
  API. Never resend a blocked question or evidence through another model,
  plugin, browser, or direct gateway call.
- Never read, enumerate, move, rename, or delete NAS files from this Skill.
  Ingestion discovery belongs to the server-side read-only scanner.
- Never bypass `source_available=false`, an unavailable count, or a source
  integrity warning by reusing cached text, a derived preview, or a direct
  filesystem path. Ask an administrator to restore the exact source and run
  server-side reconciliation.
- Treat metadata confirmation and `candidate → current` promotion as separate
  founder-controlled actions. Never infer either approval from a filename,
  modified time, or an earlier review proposal.
- Automatic asset ingestion never makes an asset `current`, canonical, final,
  or externally approved. Source-integrity, confidentiality, and department
  authorization checks still apply.
- Publication must preserve superseded versions and their effective dates.
  Never delete or overwrite historical originals as part of promotion.
- Never send a department, role, or permission claim supplied by the user as authorization; the query API must derive authorization from the verified local session and, after migration, the verified Feishu identity.
- Treat contracts, budgets, profit, minors' information, and personnel evaluations as restricted.
- Do not expose NAS paths or internal citations in externally shared client materials unless requested and approved.
- Prefer final proposals and closing reports over drafts; mention conflicts between sources.
- For new deliverables, exclude `superseded`, `expired`, `draft`, and unverified facts unless explicitly shown as history.
- For numeric claims, use the exact source and date.
- State `资料中未找到` when evidence is absent.
