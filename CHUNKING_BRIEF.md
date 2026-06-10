# SemaFlow Stage 4: Chunking Script

## Goal
Build `app/corpus/chunk.py` that reads all markdown corpus files, splits 
them into chunks respecting markdown structure, and outputs a JSON file 
for inspection. Does NOT touch the database.

## Inputs
All `.md` files under `app/corpus/docs/`:
- `data_dictionary/` → 9 files
- `policy/` → 3 files
- `categories/` → 12 files

Total: 24 source documents.

## Doc type mapping
- `app/corpus/docs/data_dictionary/*.md` → `doc_type="data_dictionary"`
- `app/corpus/docs/policy/*.md` → `doc_type="policy"`
- `app/corpus/docs/categories/*.md` → `doc_type="category_def"`

## Chunking strategy
Two-pass: markdown-header-aware split first, then fixed-size within 
each section.

### Pass 1: split on H2 headers (`## section name`)
- The H1 (`# Title`) is the document title. Do NOT split on it. Carry 
  it as parent context for every chunk from that doc.
- Each `## Section` becomes a section boundary.
- Do NOT split on H3 or deeper.
- Sections shorter than the chunk size become one chunk.

### Pass 2: fixed-size within section if section is too long
- chunk_size = 256 tokens
- overlap = 32 tokens
- Use the sentence-transformers `all-MiniLM-L6-v2` tokenizer for the 
  token count, since that is the embedding model in the next step.
- Overlap means the last 32 tokens of chunk N become the first 32 tokens 
  of chunk N+1.

## Chunk metadata
Each chunk in the output JSON:

```json
{
  "chunk_id": "uuid-string",
  "source": "fact_orders.md",
  "doc_type": "data_dictionary",
  "doc_title": "fact_orders",
  "section": "Quirks worth knowing",
  "chunk_index": 0,
  "char_start": 1245,
  "char_end": 1782,
  "token_count": 198,
  "content": "..."
}
```

`chunk_index` is sequential within the source file (0, 1, 2...).
`char_start` and `char_end` are offsets into the original markdown file.

## Output
Write the full chunk array to `app/corpus/chunks.json`, pretty-printed 
with `indent=2`.

## Dependencies
- `sentence-transformers` (for the tokenizer only at this step, no 
  embeddings yet)
- stdlib `pathlib`, `json`, `uuid`, `re`
- Do NOT install langchain. Roll the markdown split yourself with a 
  simple regex on `^## `.
- Install with: `python -m pip install sentence-transformers`

## Constraints
- Single file. No premature abstraction.
- Type hints on every function.
- Use `logging` for any output, not print, except for the validation 
  summary at the end which goes to stdout.
- Load via `pathlib.Path` walk, not os.walk.

## Validation (run after building, before declaring done)
Print to stdout:
- Total chunk count
- Chunks per doc_type (data_dictionary / policy / category_def)
- Token count stats: min / max / mean / median
- Any chunks that exceed 256 tokens (should be zero or near-zero, only 
  edge cases from tokenizer boundaries)
- 3 randomly sampled chunks (full metadata + first 200 chars of content)

## What NOT to do
- Do NOT embed anything. Embedding is the next script.
- Do NOT touch Postgres. The migration is the next script.
- Do NOT suggest semantic chunking, HyDE, or LLM-based splitting. These 
  are deferred per the locked Stage 4 scope in CLAUDE.md.
- Do NOT use langchain text splitters. Custom code is clearer here.
- Do NOT create a CLI with argparse. Hardcode the input dir and output 
  path. This script runs once per corpus update.

## After building
1. Run `python app/corpus/chunk.py` from the project root.
2. Inspect `app/corpus/chunks.json` manually (open in editor, scroll).
3. Confirm the validation summary looks sane.
4. If anything is off (chunks too short, sections missing, tokens 
   miscounted), surface it and ask before "fixing" by adding complexity.