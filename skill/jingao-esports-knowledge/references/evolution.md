# 知识库自我进化

## Goal

Continuously turn newly approved company activity into proposed updates to maintained canonical artifacts, while preserving evidence, style, and human control.

This is controlled evolution, not autonomous publication.

## Maintained artifacts

Register each artifact with:

`artifact_id`, `name`, `current_document_id`, `template_id`, `owner`, `reviewers`, `cutoff_date`, `review_cadence`, `audience`, `disclosure_level`, `section_map`, `next_review_at`.

Examples:

- company introduction deck;
- corporate capability deck;
- case-library deck;
- team and expert profile;
- qualification and awards sheet;
- standard business-line proposals.

## Change detection

For a company introduction approved in February, examine approved changes from the following day through the June review date:

- completed or accepted projects;
- confirmed activities and participant data;
- verified tournament or team results;
- new clients or partners approved for disclosure;
- new qualifications, awards, media coverage, and milestones;
- changed team biographies and business capabilities;
- approved photos, charts, videos, and reusable slides;
- facts that became invalid and must be removed.

Ignore drafts, proposals that were never executed, unconfirmed results, restricted information, duplicate exports, and assets without usage permission.

## Candidate score

Score each candidate:

- strategic significance: 0–5;
- evidence strength: 0–5;
- external disclosure approval: required;
- freshness: 0–5;
- audience relevance: 0–5;
- visual asset quality: 0–5;
- novelty versus the current deck: 0–5.

Reject candidates without evidence or disclosure approval. Route borderline candidates to review.

Apply hard gates before scoring. A candidate is ineligible when its primary
source is unavailable, not current, not final where finality matters, outside
the verified caller's permission, or lacks external-disclosure approval for an
external artifact. Do not compensate for a failed hard gate with a high score.

For eligible candidates, normalize the six 0–5 scores to 100 points:

- 80–100: `material`, include in the owner digest and proposed change plan;
- 60–79: `review`, show as an optional candidate with the unresolved decision;
- below 60: `defer`, retain in the audit digest but do not change the deck.

Deduplicate candidates that resolve to the same primary fact, event, result, or
asset. Keep the strongest primary evidence and list corroborating sources.

## Template understanding

Extract a section map from the approved deck:

- slide role and narrative purpose;
- required fields;
- maximum content density;
- layout and visual hierarchy;
- allowed asset types;
- ordering rules;
- whether the slide is evergreen, data-driven, or case-driven.

Map each update candidate to an existing slide role. Add a slide only when no existing role can hold an important new fact without damaging clarity.

## Change plan

Before producing a deck, show:

| Slide / topic | Action | Current content | Proposed content | Evidence | Reason | Confidence |
|---|---|---|---|---|---|---|

Allowed actions: `retain`, `update`, `replace`, `add`, `move_to_appendix`, `remove`.

When sources conflict, emit `conflict` instead of an allowed action and stop
that topic from entering a review deck. When a current fact has expired but no
approved replacement exists, propose `remove` or `move_to_appendix`; never
invent a replacement.

## Output states

1. `generated_candidate`: AI-produced update, never employee-default.
2. `under_review`: owner and reviewers inspect changes and citations.
3. `approved_current`: becomes the employee-default artifact.
4. `superseded`: prior current version remains in history.

Approval must atomically promote the new artifact and supersede the old one.

## Monthly operation

1. Register the already-current baseline and its cutoff, owner, audience,
   section map, confidentiality, and cadence.
2. Let the daily worker start a persistent review when `next_review_at` is due,
   or let an authorized user start it manually.
3. Review persisted candidates. Revalidate the primary source at decision time.
4. Let the founder explicitly accept or reject every material/review candidate.
   External acceptance also records disclosure approval.
5. Generate the deterministic change plan only after conflicts are resolved
   and all high-value candidates are decided.
6. Generate a review deck only after the plan is accepted. This remains a
   human-led PPT workflow; it is not yet a server endpoint.
7. Validate all citations, numbers, names, dates, image rights, and layout.
8. Close the review. This updates `last_reviewed_at` and `next_review_at` but
   deliberately leaves `cutoff_date` unchanged.
9. Publish the reviewed deck through the separate document-publication gate.
10. After the new deck is already current and directly supersedes the old
    baseline, update the maintained artifact baseline and cutoff.

If no material changes exist, retain the current version and record the review.

## Digest contract

Return:

`artifact`, `cutoff_date`, `reviewed_through`, `eligible_count`,
`material_count`, `review_count`, `deferred_count`, `conflict_count`,
`candidates`, `missing_evidence`, `next_action`.

Each candidate carries the target section, proposed action, score breakdown,
primary source, corroborating sources, disclosure state, confidence, and the
reason it is new relative to the approved artifact.

The server exposes `POST /v1/evolution/digest` for a temporary deterministic
check and a persistent workflow:

- `GET/POST /v1/evolution/artifacts`;
- `GET /v1/evolution/baseline-documents`;
- `GET /v1/evolution/artifacts/{id}`;
- `POST /v1/evolution/artifacts/{id}/runs`;
- `GET /v1/evolution/runs/{id}`;
- `POST /v1/evolution/candidates/{id}/decision`;
- `POST /v1/evolution/runs/{id}/change-plan`;
- `POST /v1/evolution/runs/{id}/close`;
- `POST /v1/evolution/artifacts/{id}/baseline`.

All detection and plan generation is deterministic and local-only. The service
does not call an LLM, generate a deck, publish a document, or automatically
advance an artifact cutoff.

`eligible_count` means the evidence passed current/final/source/permission
gates. It does not mean externally publishable. External candidates begin as
`needs_founder_approval` and remain blocked until the verified founder enters
`确认纳入并允许对外披露`. Internal acceptance requires `确认纳入变更计划`.
Rejection requires `确认不纳入`.

At approval and change-plan time, the server rechecks document identity,
current status, finality, project confirmation, citable text, source health,
and SHA-256 identity. A stale candidate cannot enter a plan.

Review-deck generation and a single atomic “generate, publish, update baseline”
operation remain deliberately unimplemented. Publication and baseline update
stay separate so a generated plan can never become employee-default truth.

## Guardrails

- Never infer project completion from a proposal.
- Never describe a team result without a confirmed source and date.
- Never expose a client, partner, minor, contract, budget, or internal metric without disclosure permission.
- Never delete the previous approved artifact.
- Never compress material changes so aggressively that the deck becomes misleading.
- Never let generated summaries become evidence for later generations; trace to primary sources.
- Never treat a completed review as permission to advance the cutoff.
- Never update a maintained artifact to a candidate or generated deck; the new
  baseline must already be current and must directly supersede the old one.

