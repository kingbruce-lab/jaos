# 方案与 PPT 工作流

The employee-facing default is free-form evidence-grounded writing, not a
fixed proposal wizard. Start with `jingao_knowledge.py writing` to retrieve
authorized material and create an editable outline or draft. Use the legacy
eight-slide endpoint only when the user explicitly requests that standard
training-proposal format.

## Fast editable draft

Use the internal API when the request fits the standard eight-slide training
proposal:

```powershell
python scripts/jingao_knowledge.py proposal-pptx `
  --title "高校电竞人才培养项目" `
  --client "客户待确认" `
  --objective "建立人才培养与实践路径" `
  --audience "高校学生" `
  --duration "6周" `
  --deliverables "课程、实训成果与结案报告" `
  --output "提案初稿.pptx"
```

The generated deck is editable. It contains Brief-derived copy, generic
proposal-framework language, authorization-filtered candidate titles, visible
`待确认` markers, and a `[Sources]` block in every slide's speaker notes.
It is an internal draft, not an approved client-facing artifact.

Use the presentation-creation skill for custom narrative, additional slides,
charts, external imagery, or final visual polish. Render every final slide and
fix overflow before delivery.

## Proposal evidence table

Before authoring slides, create:

| Proposed module | Historical source | Evidence | Adaptation | Risk |
|---|---|---|---|---|

## Recommended deck structure

1. Cover
2. Understanding of the client and opportunity
3. Objectives and success measures
4. Overall solution
5. Core modules
6. Curriculum / training / competition / operations design
7. Execution plan and responsibilities
8. Timeline
9. Team and verified capabilities
10. Historical cases
11. Risk controls
12. Budget framework or next steps
13. Evidence appendix

Adapt the structure to the task; do not force irrelevant sections.

## Evidence rules

- Use company facts only when retrieved.
- Keep new recommendations visibly separate from historical outcomes.
- Add source title, version, page, and retrieval date to the appendix.
- Remove internal NAS paths from client-facing exports.
- Never present a downloaded draft as approved or `current`; a business owner
  must confirm facts, citations, scope, and disclosure before external use.
