"""
KrashiMitra RAG Indexer
=======================
Indexes agriculture knowledge into ChromaDB.
Sources:
  1. data/agri_knowledge.json  (seed data)
  2. uploads/*.pdf             (admin-uploaded PDFs - Phase 9)

Run once to build the index:
  python -m rag.indexer
"""

import json
import os
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
DATA_FILE   = ROOT / "data" / "agri_knowledge.json"
UPLOAD_DIR  = ROOT / "uploads"
CHROMA_DIR  = ROOT / "rag" / "chroma_db"

COLLECTION_NAME = "krashi_mitra_knowledge"
CHUNK_SIZE      = 300   # characters per chunk
CHUNK_OVERLAP   = 50


# ── Chunker ───────────────────────────────────────────────────────────
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start  = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end].strip())
        start += size - overlap
    return [c for c in chunks if len(c) > 30]  # skip tiny chunks


# ── Embedding function (sentence-transformers, avoids ChromaDB default) ──
_ef = None
def get_embedding_function():
    global _ef
    if _ef is None:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        _ef = SentenceTransformerEmbeddingFunction(
            model_name="intfloat/multilingual-e5-small"
        )
    return _ef

# ── Get or create ChromaDB collection ────────────────────────────────
def get_collection():
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
        embedding_function=get_embedding_function(),
    )
    return collection


# ── Index seed JSON data ───────────────────────────────────────────────
def index_json(collection, force: bool = False) -> int:
    """Index all entries from agri_knowledge.json."""
    if not DATA_FILE.exists():
        print(f"[indexer] Seed file not found: {DATA_FILE}")
        return 0

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        entries = json.load(f)

    indexed = 0
    for entry in entries:
        doc_id   = entry["id"]
        content  = entry["content"]
        metadata = {
            "title":  entry.get("title", ""),
            "crop":   entry.get("crop", "general"),
            "season": entry.get("season", "all"),
            "topic":  entry.get("topic", ""),
            "tags":   ", ".join(entry.get("tags", [])),
            "source": "seed_data",
        }

        # Skip if already indexed (unless force re-index)
        if not force:
            existing = collection.get(ids=[doc_id])
            if existing["ids"]:
                continue

        chunks = chunk_text(content)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_c{i}"
            collection.upsert(
                ids=[chunk_id],
                documents=[chunk],
                metadatas=[{**metadata, "chunk_index": i, "parent_id": doc_id}],
            )
        indexed += 1

    return indexed


# ── Index uploaded PDFs ───────────────────────────────────────────────
def index_pdf(collection, pdf_path: Path) -> int:
    """Extract text from PDF and index into ChromaDB."""
    try:
        import pdfplumber
    except ImportError:
        print("[indexer] pdfplumber not installed. Run: pip install pdfplumber")
        return 0

    doc_id = pdf_path.stem.replace(" ", "_").lower()
    chunks_indexed = 0

    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not full_text.strip():
        print(f"[indexer] No text extracted from {pdf_path.name}")
        return 0

    chunks = chunk_text(full_text)
    for i, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}_c{i}"
        collection.upsert(
            ids=[chunk_id],
            documents=[chunk],
            metadatas=[{
                "title":       pdf_path.name,
                "crop":        "general",
                "season":      "all",
                "topic":       "pdf_upload",
                "source":      "pdf",
                "chunk_index": i,
                "parent_id":   doc_id,
            }],
        )
        chunks_indexed += 1

    return chunks_indexed


# ── Main ──────────────────────────────────────────────────────────────
def run_indexing(force: bool = False):
    print("[indexer] Starting KrashiMitra RAG indexing...")
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    collection = get_collection()

    # Index seed knowledge
    n = index_json(collection, force=force)
    print(f"[indexer] Seed data: {n} new entries indexed")

    # Index any uploaded PDFs
    pdf_count = 0
    if UPLOAD_DIR.exists():
        for pdf_file in UPLOAD_DIR.glob("*.pdf"):
            chunks = index_pdf(collection, pdf_file)
            print(f"[indexer] PDF '{pdf_file.name}': {chunks} chunks indexed")
            pdf_count += 1

    total = collection.count()
    print(f"[indexer] Total chunks in ChromaDB: {total}")
    print("[indexer] ✅ Indexing complete")
    return total


if __name__ == "__main__":
    force = "--force" in sys.argv
    run_indexing(force=force)