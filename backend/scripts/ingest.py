"""Data ingestion script: Download, chunk, embed, and store legal documents."""

import os
import sys
import json
import re
import hashlib
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datasets import load_dataset
from tqdm import tqdm

from src.core.config import get_settings
from src.embeddings.embedding_service import embed_texts
from src.embeddings.vector_store import create_collection, upsert_documents

settings = get_settings()

DATA_DIR = Path(__file__).parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"


def download_dataset():
    """Download the Vietnamese law corpus from HuggingFace."""
    print("📥 Downloading dataset from HuggingFace...")
    ds = load_dataset("kiil-lab/vietnamese-law-corpus", split="train")
    print(f"✅ Downloaded {len(ds)} documents")
    return ds


def filter_labor_law(ds) -> list:
    """Filter dataset for Labor Law related documents.

    Looks for documents mentioning labor law keywords.
    """
    print("🔍 Filtering for Labor Law documents...")
    labor_keywords = [
        "lao động", "Lao động", "LAO ĐỘNG",
        "bộ luật lao động", "luật lao động",
        "hợp đồng lao động", "người lao động", "người sử dụng lao động",
        "tiền lương", "bảo hiểm xã hội", "nghỉ phép",
        "sa thải", "kỷ luật lao động", "an toàn lao động",
        "công đoàn", "tranh chấp lao động", "thời giờ làm việc",
    ]

    labor_docs = []
    columns = ds.column_names

    for row in tqdm(ds, desc="Filtering"):
        # Try to find text content - adapt based on actual column names
        text = ""
        for col in columns:
            val = row.get(col, "")
            if isinstance(val, str):
                text += " " + val

        # Check if document is related to labor law
        text_lower = text.lower()
        if any(keyword.lower() in text_lower for keyword in labor_keywords):
            labor_docs.append(row)

    print(f"✅ Found {len(labor_docs)} Labor Law documents out of {len(ds)} total")
    return labor_docs


def chunk_documents(docs: list, columns: list) -> list:
    """Chunk documents by article (Điều).

    Each chunk contains one complete article with metadata.
    """
    print("✂️ Chunking documents...")
    chunks = []

    article_pattern = re.compile(r"(Điều\s+\d+[a-z]?\.?\s*[^\n]*)")

    for doc in tqdm(docs, desc="Chunking"):
        # Build full text from all columns
        text = ""
        metadata = {}
        for col in columns:
            val = doc.get(col, "")
            if isinstance(val, str):
                if len(val) > 500:  # Likely content column
                    text = val
                else:  # Likely metadata column
                    metadata[col] = val

        if not text:
            continue

        # Try to split by articles (Điều)
        articles = re.split(r"(?=Điều\s+\d+)", text)

        if len(articles) > 1:
            for article_text in articles:
                article_text = article_text.strip()
                if not article_text or len(article_text) < 50:
                    continue

                # Extract article number
                match = article_pattern.match(article_text)
                article_name = match.group(1).strip() if match else "N/A"

                chunk_id = hashlib.md5(article_text[:200].encode()).hexdigest()
                chunks.append({
                    "id": chunk_id,
                    "text": article_text,
                    "metadata": {
                        "article": article_name,
                        "law_name": metadata.get("ten_van_ban", metadata.get("title", "Bộ luật Lao động")),
                        "source": "kiil-lab/vietnamese-law-corpus",
                        **{k: v for k, v in metadata.items() if isinstance(v, str) and len(v) < 200},
                    },
                })
        else:
            # Document doesn't split into articles, use as single chunk
            if len(text) > settings.chunk_size:
                # Split into overlapping chunks
                for i in range(0, len(text), settings.chunk_size - settings.chunk_overlap):
                    chunk_text = text[i : i + settings.chunk_size]
                    if len(chunk_text) < 50:
                        continue
                    chunk_id = hashlib.md5(chunk_text[:200].encode()).hexdigest()
                    chunks.append({
                        "id": chunk_id,
                        "text": chunk_text,
                        "metadata": {
                            "article": "N/A",
                            "law_name": metadata.get("ten_van_ban", metadata.get("title", "Bộ luật Lao động")),
                            "source": "kiil-lab/vietnamese-law-corpus",
                            **{k: v for k, v in metadata.items() if isinstance(v, str) and len(v) < 200},
                        },
                    })
            else:
                chunk_id = hashlib.md5(text[:200].encode()).hexdigest()
                chunks.append({
                    "id": chunk_id,
                    "text": text,
                    "metadata": {
                        "article": "N/A",
                        "law_name": metadata.get("ten_van_ban", metadata.get("title", "Bộ luật Lao động")),
                        "source": "kiil-lab/vietnamese-law-corpus",
                        **{k: v for k, v in metadata.items() if isinstance(v, str) and len(v) < 200},
                    },
                })

    print(f"✅ Created {len(chunks)} chunks")
    return chunks


def save_chunks(chunks: list):
    """Save processed chunks to JSONL file."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "labor_law_chunks.jsonl"

    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"💾 Saved {len(chunks)} chunks to {output_path}")
    return output_path


def embed_and_store(chunks: list):
    """Embed chunks and store in Qdrant."""
    print("🧬 Embedding chunks and storing in Qdrant...")

    # Create collection
    create_collection(vector_size=768)  # Gemini text-embedding-004 outputs 768 dims

    # Process in batches
    batch_size = 50
    total_batches = (len(chunks) + batch_size - 1) // batch_size

    for i in tqdm(range(0, len(chunks), batch_size), total=total_batches, desc="Embedding & storing"):
        batch = chunks[i : i + batch_size]

        texts = [c["text"] for c in batch]
        ids = [c["id"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        # Embed
        embeddings = embed_texts(texts)

        # Store in Qdrant
        upsert_documents(
            ids=list(range(i, i + len(batch))),
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    print(f"✅ Stored {len(chunks)} vectors in Qdrant")


def main():
    """Run the full ingestion pipeline."""
    print("=" * 60)
    print("🚀 LEGAL DATA INGESTION PIPELINE")
    print("=" * 60)

    # Step 1: Download
    ds = download_dataset()
    columns = ds.column_names
    print(f"📋 Dataset columns: {columns}")

    # Step 2: Filter for Labor Law
    labor_docs = filter_labor_law(ds)

    if not labor_docs:
        print("⚠️ No Labor Law documents found. Using all documents instead.")
        labor_docs = [row for row in ds]

    # Step 3: Chunk
    chunks = chunk_documents(labor_docs, columns)

    # Step 4: Save processed data
    save_chunks(chunks)

    # Step 5: Embed and store in Qdrant
    embed_and_store(chunks)

    print("\n" + "=" * 60)
    print("✅ INGESTION COMPLETE!")
    print(f"📊 Total chunks stored: {len(chunks)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
