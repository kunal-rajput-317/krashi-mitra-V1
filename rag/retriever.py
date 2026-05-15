"""
KrashiMitra RAG Retriever
=========================
Searches ChromaDB for relevant agriculture context
given a farmer's question.

Returns top-k chunks to inject into the AI prompt.
"""

from pathlib import Path
from rag.indexer import get_collection, CHROMA_DIR, run_indexing

TOP_K = 4   # number of chunks to retrieve


def retrieve(query: str, crop: str = "general", top_k: int = TOP_K) -> list[dict]:
    """
    Semantic search for relevant agriculture knowledge.

    Returns list of dicts:
      { "text": ..., "title": ..., "crop": ..., "score": ... }
    """
    # Auto-index if DB is empty
    if not CHROMA_DIR.exists() or not any(CHROMA_DIR.iterdir()):
        run_indexing()

    collection = get_collection()

    if collection.count() == 0:
        return []

    # Build query — boost with crop context if not "general"
    enriched_query = query
    if crop and crop.lower() not in ["general", "other", ""]:
        enriched_query = f"{crop} farming: {query}"

    results = collection.query(
        query_texts=[enriched_query],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    docs      = results["documents"][0]
    metas     = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, dist in zip(docs, metas, distances):
        similarity = round(1 - dist, 4)  # cosine distance → similarity
        if similarity < 0.55:            # skip irrelevant chunks (raised from 0.3)
            continue
        chunks.append({
            "text":     doc,
            "title":    meta.get("title", ""),
            "crop":     meta.get("crop", ""),
            "topic":    meta.get("topic", ""),
            "score":    similarity,
            "source":   meta.get("source", ""),
        })

    # Sort by relevance
    chunks.sort(key=lambda x: x["score"], reverse=True)
    return chunks


def build_context_prompt(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a context block
    to inject into the Gemini/Ollama prompt.
    """
    if not chunks:
        return ""

    lines = ["नीचे दी गई कृषि जानकारी के आधार पर उत्तर दें:\n"]
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"[संदर्भ {i}] {chunk['title']}")
        lines.append(chunk["text"])
        lines.append("")

    return "\n".join(lines)


def retrieve_with_context(query: str, crop: str = "general") -> tuple[list[dict], str]:
    """
    Convenience function: retrieve chunks + build prompt context string.
    Returns (chunks, context_string)
    """
    chunks  = retrieve(query, crop)
    context = build_context_prompt(chunks)
    return chunks, context