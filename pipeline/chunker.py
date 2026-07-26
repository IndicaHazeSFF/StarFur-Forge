from pathlib import Path
import re


def extract_frontmatter(text: str):
    """
    Extract simple YAML-style front matter from the beginning
    of a Markdown document.
    """
    metadata = {}

    if not text.startswith("---"):
        return metadata, text

    match = re.match(
        r"^---\s*\n(.*?)\n---\s*\n",
        text,
        flags=re.DOTALL,
    )

    if not match:
        return metadata, text

    frontmatter = match.group(1)

    for line in frontmatter.splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        metadata[key.strip()] = value.strip()

    remaining_text = text[match.end():]

    return metadata, remaining_text


def split_scenes(text: str):
    """
    Split Markdown on horizontal rules used as scene breaks.
    """
    return re.split(
        r"\n\s*---\s*\n",
        text,
    )


def split_paragraphs(text: str):
    """
    Split manuscript text into paragraph-like units.

    Supports both:
    - Markdown paragraphs separated by blank lines
    - Imported manuscript prose where each paragraph is
      separated by a single newline
    """
    lines = text.splitlines()

    paragraphs = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        paragraphs.append(line)

    return paragraphs


def split_oversized_paragraph(
    paragraph: str,
    max_chars: int,
):
    """
    Emergency fallback for a single paragraph that exceeds
    max_chars.

    Prefer sentence boundaries rather than cutting blindly.
    """
    if len(paragraph) <= max_chars:
        return [paragraph]

    sentences = re.split(
        r"(?<=[.!?])\s+",
        paragraph,
    )

    pieces = []
    current = []

    for sentence in sentences:

        candidate = " ".join(
            current + [sentence]
        )

        if current and len(candidate) > max_chars:
            pieces.append(
                " ".join(current)
            )
            current = [sentence]

        else:
            current.append(sentence)

    if current:
        pieces.append(
            " ".join(current)
        )

    return pieces


def prepare_units(
    scene_text: str,
    max_chars: int,
):
    """
    Produce safe paragraph/sentence units for chunking.
    """
    paragraphs = split_paragraphs(scene_text)

    units = []

    for paragraph in paragraphs:
        units.extend(
            split_oversized_paragraph(
                paragraph,
                max_chars,
            )
        )

    return units


def chunk_scene(
    scene_text: str,
    scene_index: int,
    max_chars: int = 1200,
    overlap_paragraphs: int = 1,
):
    """
    Break one scene into paragraph-aware chunks.
    """
    units = prepare_units(
        scene_text,
        max_chars,
    )

    chunks = []
    current = []
    current_heading = None

    for unit in units:

        if unit.startswith("#"):
            current_heading = (
                unit
                .lstrip("#")
                .strip()
            )

        candidate = "\n\n".join(
            current + [unit]
        )

        if (
            current
            and len(candidate) > max_chars
        ):
            chunks.append(
                {
                    "text": "\n\n".join(current),
                    "heading": current_heading,
                    "scene_index": scene_index,
                }
            )

            if overlap_paragraphs > 0:
                current = current[
                    -overlap_paragraphs:
                ]
            else:
                current = []

            current.append(unit)

        else:
            current.append(unit)

    if current:
        chunks.append(
            {
                "text": "\n\n".join(current),
                "heading": current_heading,
                "scene_index": scene_index,
            }
        )

    return chunks


def chunk_markdown(
    path: Path,
    max_chars: int = 1200,
    overlap_paragraphs: int = 1,
):
    """
    Read a Markdown document, extract frontmatter,
    split into scenes, and produce retrieval chunks.
    """
    text = path.read_text(
        encoding="utf-8"
    )

    frontmatter, text = extract_frontmatter(
        text
    )

    scenes = split_scenes(text)

    chunks = []

    for scene_index, scene in enumerate(scenes):

        scene = scene.strip()

        if not scene:
            continue

        scene_chunks = chunk_scene(
            scene,
            scene_index,
            max_chars=max_chars,
            overlap_paragraphs=overlap_paragraphs,
        )

        for chunk in scene_chunks:
            chunk["frontmatter"] = frontmatter

        chunks.extend(scene_chunks)

    return chunks