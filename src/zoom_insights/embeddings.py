"""Embedding and retrieval functionality for meeting transcripts using ChromaDB and sentence-transformers."""

import os
import re
from pathlib import Path
from typing import Optional

try:
    import chromadb
except ImportError:
    chromadb = None  # type: ignore

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore


class ChromaEmbedder:
    """Manages embeddings using ChromaDB with persistent storage."""

    def __init__(self, embeddings_dir: str):
        """Initialize ChromaDB with persistent client.

        Args:
            embeddings_dir: Path to store embeddings database
        """
        if chromadb is None:
            raise RuntimeError(
                "chromadb not installed. Install with: pip install chromadb>=0.5.0"
            )

        self.embeddings_dir = embeddings_dir
        Path(embeddings_dir).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=embeddings_dir)

    def get_or_create_collection(self, collection_name: str):
        """Get or create a ChromaDB collection.

        Args:
            collection_name: Name of the collection (e.g., meeting_<uuid>)

        Returns:
            ChromaDB collection object
        """
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )


def _chunk_transcript(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split transcript into chunks by word boundaries with overlap.

    Args:
        text: Full transcript text
        chunk_size: Target words per chunk
        overlap: Words to overlap between chunks

    Returns:
        List of text chunks
    """
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i : i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += chunk_size - overlap

    return chunks


def _extract_timestamp(transcript: str, line_index: int) -> str:
    """Extract timestamp from transcript line.

    Attempts to find HH:MM:SS format timestamps in the transcript.
    Falls back to speaker labels if available.

    Args:
        transcript: Full transcript text
        line_index: Index in transcript (not used but kept for interface compatibility)

    Returns:
        Timestamp string or empty string if not found
    """
    lines = transcript.split("\n")
    if line_index < len(lines):
        line = lines[line_index]
        # Look for HH:MM:SS pattern
        match = re.search(r"\b(\d{1,2}):(\d{2}):(\d{2})\b", line)
        if match:
            return match.group(0)
        # Look for speaker labels like "Speaker 1:" or "Alice:"
        speaker_match = re.search(r"^([A-Za-z\s]+):\s", line)
        if speaker_match:
            return speaker_match.group(1).strip()
    return ""


def store_transcript_embeddings(
    transcript: str,
    meeting_uuid: str,
    meeting_title: str,
    embeddings_dir: str,
) -> int:
    """Store transcript chunks in ChromaDB with embeddings.

    Args:
        transcript: Full meeting transcript text
        meeting_uuid: Unique identifier for the meeting
        meeting_title: Human-readable meeting title
        embeddings_dir: Directory to store embeddings

    Returns:
        Number of chunks stored
    """
    if chromadb is None or SentenceTransformer is None:
        raise RuntimeError(
            "Missing dependencies. Install with: pip install chromadb>=0.5.0 sentence-transformers>=3.0.0"
        )

    embedder = ChromaEmbedder(embeddings_dir)
    collection_name = f"meeting_{meeting_uuid.replace('-', '_')}"
    collection = embedder.get_or_create_collection(collection_name)

    # Chunk the transcript
    chunks = _chunk_transcript(transcript)

    # Generate embeddings
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(chunks, convert_to_list=True)

    # Store in ChromaDB
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        timestamp = _extract_timestamp(transcript, i)
        collection.add(
            ids=[f"{meeting_uuid}_{i}"],
            documents=[chunk],
            embeddings=[embedding],
            metadatas=[{
                "meeting_uuid": meeting_uuid,
                "meeting_title": meeting_title,
                "chunk_index": i,
                "timestamp": timestamp,
            }],
        )

    return len(chunks)


def query_transcripts(
    query: str,
    embeddings_dir: str,
    top_k: int = 5,
) -> list[dict]:
    """Query all transcript collections for relevant chunks.

    Args:
        query: Question or search query
        embeddings_dir: Directory containing embeddings
        top_k: Number of top results to return

    Returns:
        List of dicts with: text, meeting_uuid, meeting_title, timestamp, score
    """
    if chromadb is None or SentenceTransformer is None:
        raise RuntimeError(
            "Missing dependencies. Install with: pip install chromadb>=0.5.0 sentence-transformers>=3.0.0"
        )

    if not Path(embeddings_dir).exists():
        return []

    embedder = ChromaEmbedder(embeddings_dir)

    # Generate query embedding
    model = SentenceTransformer("all-MiniLM-L6-v2")
    query_embedding = model.encode([query], convert_to_list=True)[0]

    # Search all collections
    results = []
    try:
        collections = embedder.client.list_collections()
    except Exception:
        return []

    for collection_ref in collections:
        try:
            collection = embedder.client.get_collection(collection_ref.name)
            query_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )

            if query_results and query_results["documents"]:
                for doc, metadata, distance in zip(
                    query_results["documents"][0],
                    query_results["metadatas"][0],
                    query_results["distances"][0]
                ):
                    # Convert distance to similarity score (cosine distance to similarity)
                    score = 1 - distance if distance is not None else 0.0
                    results.append({
                        "text": doc,
                        "meeting_uuid": metadata.get("meeting_uuid", ""),
                        "meeting_title": metadata.get("meeting_title", ""),
                        "timestamp": metadata.get("timestamp", ""),
                        "score": score,
                    })
        except Exception:
            continue

    # Sort by score and return top-k
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
