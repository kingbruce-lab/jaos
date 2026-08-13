from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.embeddings import embedding_allowed
from app.models import Chunk, ChunkEmbedding, Document, SourceHealth
from app.source_integrity import source_is_available


with SessionLocal() as db:
    rows = db.execute(
        select(
            ChunkEmbedding.model_name,
            func.count(ChunkEmbedding.id),
        ).group_by(ChunkEmbedding.model_name)
    ).all()
    chunks = db.scalars(
        select(Chunk).options(
            joinedload(Chunk.document).joinedload(Document.project),
            joinedload(Chunk.document).joinedload(Document.file_blob),
        )
    ).all()
    source_health = {
        row.content_hash: row
        for row in db.scalars(select(SourceHealth)).all()
    }

availability: dict[str, bool] = {}
eligible = 0
for chunk in chunks:
    document = chunk.document
    if document.content_hash not in availability:
        availability[document.content_hash] = source_is_available(
            document.file_blob,
            source_health.get(document.content_hash),
        )
    if availability[document.content_hash] and embedding_allowed(document):
        eligible += 1

for model_name, count in rows:
    print(f"{model_name}={count}")
print(f"eligible_chunks={eligible}")
