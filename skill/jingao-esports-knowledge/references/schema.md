# 知识库检索结构

## KnowledgeCategory

`id`, `key`, `name`, `active`, `sort_order`, `created_at`, `updated_at`.

The server-managed `key` is stable for permissions, projects, search, writing,
and uploads. `name` is editable display text. Always discover active
categories through `GET /v1/categories`; do not hard-code an enum in the
Skill.

## Project

`project_id`, `name`, `client`, `year`, `category_key`, `owner`, `status`, `region`, `budget_level`, `confidentiality`, `objectives`, `outcomes`.

## Document

`document_id`, `project_id`, `title`, `role`, `version`, `is_final`, `knowledge_status`, `effective_from`, `effective_to`, `supersedes_document_id`, `owner`, `next_review_at`, `modified_at`, `nas_path`, `confidentiality`, `content_hash`.

Document roles: `brief`, `proposal`, `budget`, `contract`, `execution`, `courseware`, `asset`, `data`, `closing_report`, `retrospective`.

## Passage

`passage_id`, `document_id`, `page`, `section`, `text`, `image_refs`, `table_refs`, `embedding`, `permission_scope`.

## KnowledgeBlock

`block_id`, `type`, `domain`, `title`, `summary`, `source_passage_ids`, `review_status`, `valid_from`, `valid_to`.

Block types: capability, case, course, SOP, quotation_item, metric, risk, lesson, reusable_slide.

Search results must carry source identifiers and permission scope. A generated summary is not a primary source.

## CanonicalTopic

`topic_id`, `name`, `domain`, `owner`, `current_claim_ids`, `review_cadence`, `next_review_at`.

## Claim

`claim_id`, `topic_id`, `value`, `source_passage_id`, `status`, `effective_from`, `effective_to`, `approved_by`, `approved_at`, `next_review_at`, `supersedes_claim_id`.

## Asset

`asset_id`, `type`, `project_id`, `title`, `nas_path`, `preview_path`, `usage_rights`, `subjects`, `captured_at`, `quality`, `knowledge_status`, `supersedes_asset_id`.

## MaintainedArtifact

`artifact_id`, `name`, `current_document_id`, `template_id`, `owner`, `reviewers`, `cutoff_date`, `review_cadence`, `audience`, `disclosure_level`, `section_map`, `next_review_at`.

## EvolutionCandidate

`candidate_id`, `artifact_id`, `source_claim_ids`, `source_asset_ids`, `suggested_action`, `target_section`, `significance_score`, `evidence_score`, `freshness_score`, `audience_score`, `novelty_score`, `disclosure_status`, `review_status`.
