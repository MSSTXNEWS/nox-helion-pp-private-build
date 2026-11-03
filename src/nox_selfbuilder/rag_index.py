"""Minimal RAG index. Does not claim a full ingestion pipeline."""
def index_chunks(chunks: list[str]) -> dict:
    return {"count": len(chunks), "status": "INDEXED_LOCAL", "live": False}
