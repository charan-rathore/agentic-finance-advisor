"""
ChromaDB client abstraction for finance knowledge RAG.

Supports a remote Chroma server (docker-compose) or a persistent local directory.
Swap implementation to FAISS by matching this module's public API.
"""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from core.config import get_settings


def get_collection() -> Collection:
    """Return the configured Chroma collection (creates if missing)."""
    settings = get_settings()
    # Prefer HTTP client when chroma service is on the network (see docker-compose).
    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return client.get_or_create_collection(name=settings.chroma_collection)


def add_documents(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]] | None = None,
) -> None:
    """Ingest text chunks into the vector store."""
    col = get_collection()
    col.add(ids=ids, documents=documents, metadatas=metadatas)


def query_similar(query_text: str, n_results: int = 5) -> dict[str, Any]:
    """Run a similarity search for grounding Gemini prompts."""
    col = get_collection()
    return col.query(query_texts=[query_text], n_results=n_results)
