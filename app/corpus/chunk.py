"""
Two-pass markdown chunker for SemaFlow Stage 4 corpus.
Run from project root: python app/corpus/chunk.py
Output: app/corpus/chunks.json
"""

import json
import logging
import re
import statistics
import random
import uuid
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DOCS_ROOT = Path("app/corpus/docs")
OUTPUT_PATH = Path("app/corpus/chunks.json")
CHUNK_SIZE = 256
OVERLAP = 32
TOKENIZER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

DOC_TYPE_MAP = {
    "data_dictionary": "data_dictionary",
    "policy": "policy",
    "categories": "category_def",
}


def load_tokenizer() -> Any:
    from transformers import AutoTokenizer
    logger.info("Loading tokenizer: %s", TOKENIZER_MODEL)
    return AutoTokenizer.from_pretrained(TOKENIZER_MODEL)


def extract_doc_title(content: str) -> str:
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def split_sections(content: str) -> list[tuple[str, str, int]]:
    """
    Return (section_name, section_text, char_offset) for each H2 section.
    Pre-H2 preamble is included only if it contains content beyond the H1 title.
    """
    h2_pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(h2_pattern.finditer(content))

    sections: list[tuple[str, str, int]] = []

    preamble_end = matches[0].start() if matches else len(content)
    preamble = content[:preamble_end]
    preamble_body = re.sub(r"^#[^#][^\n]*\n?", "", preamble, flags=re.MULTILINE).strip()
    if preamble_body:
        sections.append(("", preamble, 0))

    for i, match in enumerate(matches):
        section_name = match.group(1).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections.append((section_name, content[start:end], start))

    return sections


def chunk_section(
    tokenizer: Any,
    section_name: str,
    section_text: str,
    section_char_offset: int,
    source: str,
    doc_type: str,
    doc_title: str,
    chunk_index_start: int,
) -> list[dict[str, Any]]:
    encoding = tokenizer(
        section_text,
        return_offsets_mapping=True,
        add_special_tokens=False,
    )
    token_ids: list[int] = encoding["input_ids"]
    offset_mapping: list[tuple[int, int]] = encoding["offset_mapping"]

    if not token_ids:
        return []

    chunks: list[dict[str, Any]] = []
    chunk_idx = chunk_index_start
    pos = 0

    while pos < len(token_ids):
        end = min(pos + CHUNK_SIZE, len(token_ids))

        char_start = offset_mapping[pos][0]
        char_end = offset_mapping[end - 1][1]

        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "source": source,
            "doc_type": doc_type,
            "doc_title": doc_title,
            "section": section_name,
            "chunk_index": chunk_idx,
            "char_start": section_char_offset + char_start,
            "char_end": section_char_offset + char_end,
            "token_count": end - pos,
            "content": section_text[char_start:char_end],
        })

        chunk_idx += 1
        if end >= len(token_ids):
            break
        pos += CHUNK_SIZE - OVERLAP

    return chunks


def process_file(
    tokenizer: Any,
    filepath: Path,
    doc_type: str,
) -> list[dict[str, Any]]:
    content = filepath.read_text(encoding="utf-8")
    source = filepath.name
    doc_title = extract_doc_title(content)
    sections = split_sections(content)

    logger.info("  %s: %d section(s)", source, len(sections))

    all_chunks: list[dict[str, Any]] = []
    chunk_idx = 0

    for section_name, section_text, section_char_offset in sections:
        new_chunks = chunk_section(
            tokenizer,
            section_name,
            section_text,
            section_char_offset,
            source,
            doc_type,
            doc_title,
            chunk_idx,
        )
        chunk_idx += len(new_chunks)
        all_chunks.extend(new_chunks)

    return all_chunks


def collect_files() -> list[tuple[Path, str]]:
    pairs: list[tuple[Path, str]] = []
    for subdir, doc_type in DOC_TYPE_MAP.items():
        subdir_path = DOCS_ROOT / subdir
        for md_file in sorted(subdir_path.glob("*.md")):
            pairs.append((md_file, doc_type))
    return pairs


def print_validation_summary(chunks: list[dict[str, Any]]) -> None:
    token_counts = [c["token_count"] for c in chunks]
    by_type: dict[str, int] = {}
    for c in chunks:
        by_type[c["doc_type"]] = by_type.get(c["doc_type"], 0) + 1

    oversized = [c for c in chunks if c["token_count"] > CHUNK_SIZE]
    sample = random.sample(chunks, min(3, len(chunks)))

    print("\n=== Validation Summary ===")
    print(f"Total chunks: {len(chunks)}")
    print("\nChunks per doc_type:")
    for dt, count in sorted(by_type.items()):
        print(f"  {dt}: {count}")
    print("\nToken count stats:")
    print(f"  min:    {min(token_counts)}")
    print(f"  max:    {max(token_counts)}")
    print(f"  mean:   {statistics.mean(token_counts):.1f}")
    print(f"  median: {statistics.median(token_counts):.1f}")
    print(f"\nChunks exceeding {CHUNK_SIZE} tokens: {len(oversized)}")
    if oversized:
        for c in oversized:
            print(f"  {c['source']} / {c['section']} → {c['token_count']} tokens")
    print("\n--- 3 random sample chunks ---")
    for c in sample:
        print(f"\n  chunk_id:    {c['chunk_id']}")
        print(f"  source:      {c['source']}")
        print(f"  doc_type:    {c['doc_type']}")
        print(f"  section:     {c['section']}")
        print(f"  chunk_index: {c['chunk_index']}")
        print(f"  char_start:  {c['char_start']}")
        print(f"  char_end:    {c['char_end']}")
        print(f"  token_count: {c['token_count']}")
        print(f"  content[:200]: {repr(c['content'][:200])}")


def main() -> None:
    tokenizer = load_tokenizer()
    files = collect_files()
    logger.info("Found %d source files", len(files))

    all_chunks: list[dict[str, Any]] = []
    for filepath, doc_type in files:
        file_chunks = process_file(tokenizer, filepath, doc_type)
        all_chunks.extend(file_chunks)
        logger.info("  → %d chunks", len(file_chunks))

    OUTPUT_PATH.write_text(
        json.dumps(all_chunks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Written %d total chunks to %s", len(all_chunks), OUTPUT_PATH)

    print_validation_summary(all_chunks)


if __name__ == "__main__":
    main()
