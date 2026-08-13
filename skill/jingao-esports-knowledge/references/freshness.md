# 当前知识与历史知识

## Two layers

Maintain two distinct views:

- **Current canonical knowledge**: the one approved source for facts employees may use now.
- **Historical archive**: past versions, cases, proposals, assets, execution records, and retrospectives.

Default new proposals, company introductions, resumes, capability descriptions, contact details, partner lists, certifications, pricing policies, and team information to the current view. Use history only for project learning, comparison, evidence, or an explicitly requested past-date view.

## Knowledge status

Every document and claim has one status:

- `draft`: working material; never use as current fact.
- `candidate`: possibly newer; waiting for approval.
- `current`: approved and currently valid.
- `superseded`: replaced by a newer approved item.
- `expired`: no longer valid and not directly replaced.
- `historical`: preserved as case evidence, not a current company fact.
- `quarantined`: deleted, conflicting, or under investigation.

Only `current` claims may populate new company introductions automatically.

## Canonical topics

Create a canonical record for each maintained topic, for example:

- company overview;
- company milestones;
- core capabilities;
- management and project-team bios;
- active partners and clients approved for disclosure;
- current qualifications and awards;
- current business lines;
- current contact details;
- standard service modules;
- reusable case list;
- current logo and presentation template.

Each topic has an owner, review cadence, approved source, effective date, next review date, and replacement chain.

## Promotion

A later filename or modified timestamp does not prove authority. Promote a candidate to current only when:

1. its owner and topic are identified;
2. the source file and version are explicit;
3. changes from the current record are shown;
4. conflicts are resolved;
5. a designated reviewer approves it;
6. the former current version becomes superseded without being deleted.

## Claim-level freshness

Freshness belongs to individual claims, not only whole files. A company deck may contain a current logo but an outdated employee count.

Store:

`claim_id`, `topic`, `value`, `source_passage_id`, `status`, `effective_from`, `effective_to`, `approved_by`, `approved_at`, `next_review_at`, `supersedes_claim_id`.

## Search behavior

- `current`: search current canonical claims first; retrieve current documents only as supporting context.
- `history`: search archived projects and all approved historical versions.
- `as-of`: select facts whose effective interval contains the requested date.
- `all`: administrative audit only; never use for automatic drafting.

Show a warning when a current claim is past `next_review_at`, lacks an owner, or conflicts with another current claim.

## Assets

Register logos, photos, case images, diagrams, videos, and reusable slides separately from textual documents. Store preview, original path, usage rights, subjects, project, date, quality, current/historical status, and replacement relationship. Default PPT generation to current brand assets plus historical project assets relevant to the selected case.
