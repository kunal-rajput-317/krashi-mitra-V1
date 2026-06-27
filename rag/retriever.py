"""
KrashiMitra RAG Retriever
=========================
Searches ChromaDB for relevant agriculture context
given a farmer's question.

Returns top-k chunks to inject into the AI prompt.
"""

import os
from pathlib import Path
from rag.indexer import get_collection, CHROMA_DIR, run_indexing

TOP_K = 4
AUTO_INDEX_ON_ASK = os.getenv("RAG_AUTO_INDEX_ON_ASK", "false").lower() == "true"

# Maps internal crop JSON keys → natural language for better RAG enrichment.
# Using the JSON filename key directly ("wheat_up") in the ChromaDB query
# hurts semantic similarity because the index contains natural language text.
CROP_NAME_MAP: dict[str, str] = {
    "wheat_up":     "wheat गेहूँ",
    "rice_up":      "rice धान",
    "sugarcane_up": "sugarcane गन्ना",
    "rice":         "rice धान",
    "mustard":      "mustard सरसों",
    "potato":       "potato आलू",
    "maize":        "maize मक्का",
    "cotton":       "cotton कपास",
    "general":      "",   # no prefix for general
    "other":        "",
}


def retrieve(query: str, crop: str = "general", top_k: int = TOP_K) -> list[dict]:
    """
    Semantic search for relevant agriculture knowledge.
    Returns list of dicts: { text, title, crop, topic, score, source }
    """
    if not CHROMA_DIR.exists() or not any(CHROMA_DIR.iterdir()):
        if AUTO_INDEX_ON_ASK:
            run_indexing()
        else:
            print("[RAG] Chroma index missing. Run /admin/reindex from admin panel.")
            return []

    collection = get_collection()
    if collection.count() == 0:
        return []

    # Enrich query with natural language crop name (not the JSON key)
    crop_display = CROP_NAME_MAP.get((crop or "").lower(), crop or "")
    enriched_query = f"{crop_display}: {query}" if crop_display else query

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
        similarity = round(1 - dist, 4)   # cosine distance → similarity
        if similarity < 0.55:
            continue
        chunks.append({
            "text":   doc,
            "title":  meta.get("title", ""),
            "crop":   meta.get("crop", ""),
            "topic":  meta.get("topic", ""),
            "score":  similarity,
            "source": meta.get("source", ""),
        })

    chunks.sort(key=lambda x: x["score"], reverse=True)
    return chunks


def build_context_prompt(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context block for the AI prompt."""
    if not chunks:
        return ""
    lines = ["नीचे दी गई कृषि जानकारी के आधार पर उत्तर दें:\n"]
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"[संदर्भ {i}] {chunk['title']}")
        lines.append(chunk["text"])
        lines.append("")
    return "\n".join(lines)


def retrieve_with_context(query: str, crop: str = "general") -> tuple[list[dict], str]:
    """Convenience: retrieve chunks + build context string. Returns (chunks, context)."""
    chunks  = retrieve(query, crop)
    context = build_context_prompt(chunks)
    return chunks, context
