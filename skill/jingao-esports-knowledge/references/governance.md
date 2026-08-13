# 定期整理与知识治理

## Schedule

- Every 15 minutes: let the server-side read-only scanner inspect
  `99_AI入库待审核`. Require a 120-second stable-file window and deduplicate by
  SHA-256 before candidate registration.
- Nightly: verify every registered source by SHA-256, reconnect moved files
  only on an exact hash match within the knowledge root, then parse new or
  changed files, refresh indexes, and create candidates without changing
  canonical facts.
- Weekly: cluster duplicates and versions; generate change comparisons and review candidates.
- Monthly: review canonical topics, stale claims, asset replacements, and missing-closing-report lists.
- On each maintained artifact's cadence: detect material changes since its cutoff date and create an evolution digest.
- Quarterly: sample citations, permissions, backups, and restore readiness.

## Human review gates

Confidentiality display names are fixed as: `L1 - 公司公共资料`,
`L2 - 业务普通资料`, `L3 - 业务敏感资料`, and `L4 - 核心敏感资料`.
The stable codes remain `L1`-`L4` in APIs and stored records.

Ingestion uses two file classes:

- Content documents (PowerPoint, Word, Excel, PDF, and plain-text/Markdown)
  enter the human review queue. Authorized reviewers may batch-confirm L1-L3
  documents. L4 documents must be confirmed individually.
- Image, video, audio, design-source, archive, and mind-map files are
  automatically registered as `approved` historical assets. They do not enter
  the human review queue, but they remain subject to source-integrity,
  confidentiality, and department authorization checks. Automatic asset
  ingestion never marks an item final or promotes it to `current`.

Require a human to confirm:

- final version;
- whether a proposal was executed;
- confidentiality level;
- project outcomes;
- reusable pricing or contractual language;
- conflicts between proposal and closing report.
- promotion of any candidate to current canonical knowledge.
- replacement of current brand assets, company facts, biographies, partners, qualifications, or contact details.

Use two separate gates for first-release ingestion:

1. A knowledge administrator submits a metadata proposal covering project,
   client, year, domain, final-state, confidentiality, document role, and
   version. Submitting a proposal must not change the document or project.
2. The founder explicitly applies or rejects that proposal. Applying metadata
   must leave both the document and project in `candidate`.

Treat promotion from `candidate` to `current` as a separate founder decision.
Never combine metadata confirmation with canonical publication. A rejected
proposal must leave source metadata unchanged; a replacement proposal must
supersede the older pending proposal while preserving its audit history.

The publication API must verify that metadata and project assignment are
confirmed, the document is final, the source is available, and citable content
exists. It must show and require the exact complete set of current documents
that will become `superseded`; a changed set is a conflict, not an implicit
approval. Preserve originals, `valid_from`, `valid_to`, and the publication
audit event.

## Inbox scanner boundaries

- Keep the NAS mount read-only inside the knowledge service.
- Never ingest temporary files, symbolic links, path escapes, files still
  changing, unsupported formats, or files above the configured size limit.
- Record unresolved items for the founder using relative paths only. Never
  expose the NAS root path to the Skill or ordinary employees.
- Treat path, filename, inferred project, domain, role, year, version, and
  confidentiality as conservative prefill only.
- Register content documents as `candidate`. Register exempt asset formats as
  `approved` historical assets. Scanning never promotes any file to `current`
  knowledge.
- Do not let the Skill traverse or mutate NAS files. It must consume the
  authenticated API after server-side authorization and auditing.

## Source integrity

- Record a verified source-health row at ingestion and run a read-only full
  reconciliation on a nightly schedule.
- A moved or renamed source may be rebound only when its exact SHA-256 and
  size match a registered content identity inside the configured knowledge
  root.
- Missing, unreadable, size-mismatched, or hash-mismatched sources must be
  excluded from search, previews, derivatives, embeddings, backup availability
  lists, and canonical publication.
- Restoring the exact source may make it usable again, but never confirms
  metadata, final-state, confidentiality, project assignment, or canonical
  truth.
- Treat changed content as a new ingestion candidate. Never overwrite the old
  content identity or citation chain.
- Audit reconciliation with counts and duration only; do not put absolute
  paths or filenames in routine integrity audit details.

## Version rules

Use content hashes to detect duplicates. Group filename variants under the same project. Rank evidence:

1. confirmed closing report or signed acceptance;
2. confirmed execution/data report;
3. final proposal;
4. working draft;
5. generated summary.

Do not rank freshness by filename or modified time alone. Maintain explicit `current → superseded` chains and effective dates. Read `freshness.md` for canonical-topic rules.

## Deletion

Move deleted records to a 30-day quarantine. Remove them from employee search immediately, but keep an auditable tombstone. Purge source copies and derived embeddings together after approval.

## Summary format

Create a project summary with background, client need, solution, execution, results, lessons, reusable modules, risks, and source coverage. Mark missing sections explicitly.
