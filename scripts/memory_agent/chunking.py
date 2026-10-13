"""Lossless source slices with bounded preceding context."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    start: int
    end: int
    text: str


def split_text(text: str, max_bytes: int = 6000, overlap_chars: int = 160) -> list[Chunk]:
    if max_bytes < 32 or overlap_chars < 0:
        raise ValueError("max_bytes must be >=32 and overlap_chars >=0")
    chunks = []
    start = 0
    while start < len(text):
        end = start
        size = 0
        while end < len(text) and size + len(text[end].encode('utf-8')) <= max_bytes:
            size += len(text[end].encode('utf-8'))
            end += 1
        if end < len(text):
            # Prefer paragraph/sentence boundaries in the latter half of the slice.
            floor = start + (end - start) // 2
            boundaries = [text.rfind(sep, floor, end) + len(sep)
                          for sep in ('\n\n', '\n', '. ', '! ', '? ', '。')]
            end = max([b for b in boundaries if b > floor] or [end])
        chunks.append(Chunk(start, end, text[start:end]))
        if end == len(text):
            break
        start = end - min(overlap_chars, (end - start) // 4)
    return chunks
