from app.parsers import chunk_text


def test_chunk_text_preserves_document_lines() -> None:
    rows = [f"岗位{i} | 单价{i} | 数量{i} | 金额{i}" for i in range(80)]

    chunks = chunk_text("\n".join(rows), target=180, overlap=45)

    assert len(chunks) > 1
    assert all(len(chunk) <= 180 for chunk in chunks)
    assert all("\n" in chunk for chunk in chunks)
    assert all(row in "\n".join(chunks) for row in rows)


def test_chunk_text_prefers_sentence_boundaries_for_long_paragraph() -> None:
    text = "。".join(f"第{i}条电竞培训项目经验" for i in range(60)) + "。"

    chunks = chunk_text(text, target=120, overlap=20)

    assert len(chunks) > 1
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert all(chunk.endswith("。") for chunk in chunks)
