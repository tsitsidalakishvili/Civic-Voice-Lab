import re
from typing import Dict, List, Tuple


def _split_paragraphs(text: str) -> List[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text or "") if p.strip()]
    if paragraphs:
        return paragraphs
    sentences = re.split(r"(?<=[.!?])\s+", text or "")
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def normalize_text(text: str) -> Tuple[str, List[Tuple[str, int, int]]]:
    paragraphs = _split_paragraphs(text)
    normalized = "\n\n".join(paragraphs)
    offsets: List[Tuple[str, int, int]] = []
    cursor = 0
    for paragraph in paragraphs:
        start = cursor
        end = start + len(paragraph)
        offsets.append((paragraph, start, end))
        cursor = end + 2
    return normalized, offsets


def build_chunks(
    cleaned_text: str,
    headings: List[str],
    target_chars: int = 1600,
    min_chars: int = 400,
    overlap_chars: int = 200,
) -> Tuple[str, List[Dict[str, object]]]:
    normalized_text, paragraphs = normalize_text(cleaned_text)
    chunks: List[Dict[str, object]] = []
    current: List[Tuple[str, int, int]] = []
    current_len = 0
    heading_set = {heading.strip(): heading for heading in headings if heading.strip()}
    active_heading = ""

    def flush(active_heading_value: str):
        nonlocal current, current_len
        if not current:
            return
        chunk_text = "\n\n".join(item[0] for item in current)
        start_offset = current[0][1]
        end_offset = current[-1][2]
        chunks.append(
            {
                "text": chunk_text,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "section_heading": active_heading_value,
            }
        )
        if overlap_chars > 0:
            overlap: List[Tuple[str, int, int]] = []
            overlap_len = 0
            for paragraph, start, end in reversed(current):
                overlap.insert(0, (paragraph, start, end))
                overlap_len += len(paragraph) + 2
                if overlap_len >= overlap_chars:
                    break
            current = overlap
            current_len = sum(len(item[0]) for item in current) + max(0, len(current) - 1) * 2
        else:
            current = []
            current_len = 0

    for paragraph, start, end in paragraphs:
        if paragraph in heading_set:
            active_heading = paragraph
        if len(paragraph) < 6 and paragraph in heading_set:
            continue
        extra = len(paragraph) + (2 if current else 0)
        if current_len + extra > target_chars and current_len >= min_chars:
            flush(active_heading)
        current.append((paragraph, start, end))
        current_len += extra

    if current:
        flush(active_heading)

    return normalized_text, chunks
