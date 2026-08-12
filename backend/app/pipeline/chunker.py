"""文本切片规则（04 §3.5 新增：固定长度 500 字、重叠 50 字，标题/段落优先）。"""

from __future__ import annotations

import re

DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """按段落聚合切片：段落自然边界优先；超长段落按固定长度 + 重叠切分。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # 单段超长：按 chunk_size 切，保留 overlap 重叠
        if len(para) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(para):
                end = min(start + chunk_size, len(para))
                chunks.append(para[start:end])
                if end >= len(para):
                    break
                start = max(0, end - overlap)
            continue

        if current and len(current) + 1 + len(para) > chunk_size:
            chunks.append(current)
            current = para
        else:
            current = para if not current else f"{current}\n{para}"

    if current:
        chunks.append(current)
    return chunks

