from pathlib import Path
import re


def split_paragraphs(text: str):
    return [
        p.strip()
        for p in re.split(r"\n\s*\n", text)
        if p.strip()
    ]


def chunk_markdown(
    path: Path,
    max_chars: int = 1200,
    overlap_paragraphs: int = 1,
):
    text = path.read_text(encoding="utf-8")
    paragraphs = split_paragraphs(text)

    chunks = []
    current = []
    current_heading = None

    for paragraph in paragraphs:

        # Track most recent Markdown heading
        if paragraph.startswith("#"):
            current_heading = paragraph.lstrip("#").strip()

        candidate = "\n\n".join(current + [paragraph])

        if current and len(candidate) > max_chars:

            chunks.append({
                "text": "\n\n".join(current),
                "heading": current_heading,
            })

            # Carry limited context into next chunk
            if overlap_paragraphs > 0:
                current = current[-overlap_paragraphs:]
            else:
                current = []

            current.append(paragraph)

        else:
            current.append(paragraph)

    if current:
        chunks.append({
            "text": "\n\n".join(current),
            "heading": current_heading,
        })

    return chunks
