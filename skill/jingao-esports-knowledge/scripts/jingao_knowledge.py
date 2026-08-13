#!/usr/bin/env python3
"""Authenticated client for the Jingao internal knowledge service."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


PPTX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "presentationml.presentation"
)


def emit(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def api_request(
    path: str,
    *,
    method: str = "GET",
    json_body: dict | None = None,
    expect_bytes: bool = False,
):
    base = os.environ.get("JINGAO_KB_URL", "").rstrip("/")
    token = os.environ.get("JINGAO_KB_TOKEN", "")
    if not base:
        raise RuntimeError("set JINGAO_KB_URL")
    if not token:
        raise RuntimeError("set JINGAO_KB_TOKEN")
    data = None
    headers = {"Accept": PPTX_MEDIA_TYPE if expect_bytes else "application/json"}
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if expect_bytes:
                return response.read(), dict(response.headers)
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = None
        message = f"knowledge service returned HTTP {exc.code}"
        if detail:
            message += f": {detail}"
        raise RuntimeError(message) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("knowledge service is unreachable") from exc


def search_payload(args) -> dict:
    payload = {
        "query": args.query,
        "scope": args.scope,
        "retrieval": args.retrieval,
        "limit": args.limit,
    }
    if args.category:
        payload["category"] = args.category
    return payload


def proposal_payload(args) -> dict:
    return {
        "title": args.title,
        "client": args.client,
        "objective": args.objective,
        "audience": args.audience,
        "budget": args.budget,
        "geography": args.geography,
        "duration": args.duration,
        "deliverables": args.deliverables,
    }


def add_proposal_arguments(parser) -> None:
    parser.add_argument("--title", required=True)
    parser.add_argument("--client")
    parser.add_argument("--objective")
    parser.add_argument("--audience")
    parser.add_argument("--budget")
    parser.add_argument("--geography")
    parser.add_argument("--duration")
    parser.add_argument("--deliverables")


def resolve_project(name: str) -> dict:
    projects = api_request("/v1/projects")
    normalized = name.strip().casefold()
    exact = [
        item
        for item in projects
        if item.get("name", "").strip().casefold() == normalized
    ]
    candidates = exact or [
        item
        for item in projects
        if normalized in item.get("name", "").casefold()
    ]
    if not candidates:
        raise RuntimeError("资料中未找到匹配项目")
    if len(candidates) > 1:
        names = "、".join(item.get("name", "") for item in candidates[:5])
        raise RuntimeError(f"匹配到多个项目，请使用完整名称：{names}")
    return candidates[0]


def project_path(project_id: str, suffix: str = "") -> str:
    encoded = urllib.parse.quote(str(project_id), safe="")
    return f"/v1/projects/{encoded}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("categories")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--category", "--domain", dest="category")
    search.add_argument(
        "--scope",
        choices=["current", "history", "all"],
        default="current",
    )
    search.add_argument(
        "--retrieval",
        choices=["auto", "exact", "semantic", "hybrid"],
        default="auto",
    )
    search.add_argument("--limit", type=int, default=8)

    writing = sub.add_parser("writing")
    writing.add_argument("instruction")
    writing.add_argument("--category")
    writing.add_argument(
        "--scope",
        choices=["current", "history", "all"],
        default="all",
    )

    project = sub.add_parser("project")
    project.add_argument("name")

    document = sub.add_parser("document")
    document.add_argument("document_id")

    draft = sub.add_parser("proposal-draft")
    add_proposal_arguments(draft)

    pptx = sub.add_parser("proposal-pptx")
    add_proposal_arguments(pptx)
    pptx.add_argument("--output", required=True)

    args = parser.parse_args()
    try:
        if args.command == "status":
            emit(api_request("/v1/status"))
        elif args.command == "categories":
            emit(api_request("/v1/categories"))
        elif args.command == "search":
            emit(
                api_request(
                    "/v1/search",
                    method="POST",
                    json_body=search_payload(args),
                )
            )
        elif args.command == "writing":
            payload = {
                "instruction": args.instruction,
                "scope": args.scope,
            }
            if args.category:
                payload["category"] = args.category
            emit(
                api_request(
                    "/v1/writing/draft",
                    method="POST",
                    json_body=payload,
                )
            )
        elif args.command == "project":
            item = resolve_project(args.name)
            emit(api_request(project_path(item["id"])))
        elif args.command == "document":
            document_id = urllib.parse.quote(args.document_id, safe="")
            emit(api_request(f"/v1/documents/{document_id}"))
        elif args.command == "proposal-draft":
            emit(
                api_request(
                    "/v1/proposals/draft",
                    method="POST",
                    json_body=proposal_payload(args),
                )
            )
        elif args.command == "proposal-pptx":
            output = Path(args.output).expanduser().resolve()
            if output.suffix.lower() != ".pptx":
                raise RuntimeError("--output must end with .pptx")
            payload, _headers = api_request(
                "/v1/proposals/pptx",
                method="POST",
                json_body=proposal_payload(args),
                expect_bytes=True,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(payload)
            emit(
                {
                    "status": "created",
                    "output": str(output),
                    "bytes": len(payload),
                    "notice": "内部可编辑初稿；对外使用前必须审核事实与引用。",
                }
            )
    except RuntimeError as exc:
        emit({"error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
