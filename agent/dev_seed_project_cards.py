"""Seed an isolated synthetic database for local project-card UI checks."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal, init_database
from app.knowledge_cards import confirm_card, create_or_refresh_card
from app.models import Chunk, Document, FileBlob, Project, User


DEMO_PASSWORD = "Jingao-Demo-2026!"


def add_document(
    db,
    *,
    project: Project,
    title: str,
    role: str,
    page: int,
    text: str,
) -> None:
    source_dir = settings.data_dir / "demo-sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    payload = text.encode("utf-8")
    content_hash = hashlib.sha256(payload).hexdigest().upper()
    source = source_dir / f"{content_hash}.txt"
    source.write_bytes(payload)
    blob = FileBlob(
        content_hash=content_hash,
        size_bytes=len(payload),
        source_path=str(source),
    )
    document = Document(
        project=project,
        file_blob=blob,
        content_hash=content_hash,
        title=title,
        role=role,
        version="v1.0",
        is_final=True,
        knowledge_status="current",
        confidentiality="L2",
        page_count=page,
    )
    db.add_all(
        [
            blob,
            document,
            Chunk(
                document=document,
                page=page,
                chunk_index=0,
                text=text,
            ),
        ]
    )


def main() -> None:
    init_database()
    with SessionLocal() as db:
        founder = User(
            username="founder",
            display_name="京奥测试管理员",
            password_hash=hash_password(DEMO_PASSWORD),
            role="founder",
            confidentiality_ceiling="L4",
        )
        completed = Project(
            name="高校电竞人才培养示范项目",
            client="演示客户（虚构）",
            year=2026,
            domain="training",
            status="completed",
            confidentiality="L2",
            knowledge_status="current",
            confirmed=True,
        )
        missing_closing = Project(
            name="城市电竞讲师训练营",
            client="演示客户（虚构）",
            year=2026,
            domain="training",
            status="completed",
            confidentiality="L2",
            knowledge_status="current",
            confirmed=True,
        )
        db.add_all([founder, completed, missing_closing])
        db.flush()

        add_document(
            db,
            project=completed,
            title="项目需求简报",
            role="brief",
            page=1,
            text=(
                "项目背景：高校希望建立电竞人才培养路径，目标受众为在校学生，"
                "需要兼顾职业认知、技能训练与就业衔接。"
            ),
        )
        add_document(
            db,
            project=completed,
            title="项目执行方案",
            role="proposal",
            page=4,
            text=(
                "总体方案：设置行业认知、专项技能、实训演练和阶段考核四个模块，"
                "按六周计划组织教学与复盘。"
            ),
        )
        add_document(
            db,
            project=completed,
            title="项目结案报告",
            role="closing_report",
            page=12,
            text=(
                "项目结果：全部课程按计划完成并通过客户验收。复盘建议：后续项目"
                "应提前核对场地、设备和学员基础，减少临时调整风险。"
            ),
        )
        add_document(
            db,
            project=missing_closing,
            title="讲师训练营执行方案",
            role="proposal",
            page=3,
            text="执行方案：组织教学设计、试讲、互评和认证考核。",
        )
        db.commit()

        card = create_or_refresh_card(
            db,
            project=completed,
            user=founder,
        )
        confirm_card(
            db,
            project=completed,
            card=card,
            user=founder,
            note="仅用于本机界面验收的虚构资料",
        )

    print("DEMO_READY founder Jingao-Demo-2026!")


if __name__ == "__main__":
    main()
