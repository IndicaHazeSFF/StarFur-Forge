from pathlib import Path
import re
import unicodedata


INPUT_FILE = Path("canon/manuscript/manuscript.txt")
OUTPUT_DIR = Path("canon/chapters")


CHAPTER_RE = re.compile(
    r"^(Chapter\s+(\d+)\s+[—-]\s+(.+))$",
    re.MULTILINE,
)

PROLOGUE_RE = re.compile(
    r"^Prologue\s*$",
    re.MULTILINE,
)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode()

    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)

    return text.strip("-")


def write_markdown(
    number: int,
    heading: str,
    title: str,
    body: str,
):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if number == 0:
        filename = "00-prologue.md"
    else:
        filename = f"{number:02d}-{slugify(title)}.md"

    frontmatter = (
        "---\n"
        f"chapter: {number}\n"
        f'heading: "{heading}"\n'
        f'title: "{title}"\n'
        'source: "manuscript.txt"\n'
        "---\n\n"
    )

    markdown = (
        frontmatter
        + f"# {heading}\n\n"
    )

    if title and heading.lower() != "prologue":
        markdown += f"## {title}\n\n"

    markdown += body.strip() + "\n"

    (OUTPUT_DIR / filename).write_text(
        markdown,
        encoding="utf-8",
    )

    print(f"✓ {filename}")


def main():

    text = INPUT_FILE.read_text(encoding="utf-8")

    matches = []

    prologue = PROLOGUE_RE.search(text)

    if prologue:
        matches.append(
            (
                prologue.start(),
                "Prologue",
                0,
                "Prologue",
            )
        )

    for match in CHAPTER_RE.finditer(text):

        matches.append(
            (
                match.start(),
                match.group(1),
                int(match.group(2)),
                match.group(3).strip(),
            )
        )

    matches.sort(key=lambda x: x[0])

    for i, (start, heading, number, title) in enumerate(matches):

        if i + 1 < len(matches):
            end = matches[i + 1][0]
        else:
            end = len(text)

        section = text[start:end].strip()

        lines = section.splitlines()

        body = "\n".join(lines[1:]).strip()

        write_markdown(
            number=number,
            heading=heading,
            title=title,
            body=body,
        )

    print()
    print(f"Finished. Generated {len(matches)} chapter files.")


if __name__ == "__main__":
    main()
