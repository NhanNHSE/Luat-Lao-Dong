"""Data ingestion pipeline: Download Vietnamese law corpus, filter labor law, chunk, embed, store.

Uses two data sources:
1. kiil-lab/vietnamese-law-corpus — Full text of Vietnamese laws (markdown)
2. namphan1999/data-luat — Q&A pairs for legal questions

Pipeline steps:
    Download → Filter → Chunk by Điều → Deduplicate → Embed → Store in Qdrant
"""

import os
import sys
import json
import re
import hashlib
import time
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

# ─────────────────────────────────────────────────────────────
# LABOR LAW KEYWORDS — used to filter corpus
# ─────────────────────────────────────────────────────────────
LABOR_KEYWORDS = [
    # Core labor law
    "bộ luật lao động", "luật lao động",
    "hợp đồng lao động", "người lao động", "người sử dụng lao động",
    # Wages & benefits
    "tiền lương", "lương tối thiểu", "phụ cấp", "tiền thưởng",
    "trợ cấp thôi việc", "trợ cấp mất việc",
    # Working time
    "thời giờ làm việc", "thời giờ nghỉ ngơi",
    "làm thêm giờ", "tăng ca", "nghỉ phép",
    "nghỉ lễ", "nghỉ việc riêng",
    # Insurance
    "bảo hiểm xã hội", "bảo hiểm y tế", "bảo hiểm thất nghiệp",
    "bhxh", "bhyt",
    # Safety
    "an toàn lao động", "vệ sinh lao động",
    "an toàn vệ sinh lao động", "tai nạn lao động", "bệnh nghề nghiệp",
    # Discipline & disputes
    "kỷ luật lao động", "sa thải", "đơn phương chấm dứt",
    "tranh chấp lao động", "hòa giải lao động",
    "đình công",
    # Union
    "công đoàn", "tổ chức đại diện người lao động",
    # Special groups
    "lao động nữ", "thai sản", "nghỉ thai sản",
    "lao động chưa thành niên", "lao động người cao tuổi",
    "lao động nước ngoài",
    # Contracts
    "thử việc", "hợp đồng thử việc",
    "chấm dứt hợp đồng", "gia hạn hợp đồng",
    # Direct law references
    "45/2019/qh14",  # Bộ luật Lao động 2019
    "58/2014/qh13",  # Luật BHXH 2014
    "25/2014/qh13",  # Luật BHYT
    "luật việc làm",
    "luật an toàn",
]

# ─────────────────────────────────────────────────────────────
# Source 1: Vietnamese Law Corpus (kiil-lab)
# ─────────────────────────────────────────────────────────────

def download_law_corpus():
    """Download the Vietnamese law corpus from HuggingFace.

    Dataset: kiil-lab/vietnamese-law-corpus
    Columns: doc_id (int), markdown (str)
    Size: ~215K documents, 1.38GB
    """
    print("📥 Downloading kiil-lab/vietnamese-law-corpus...")
    ds = load_dataset("kiil-lab/vietnamese-law-corpus", split="train")
    print(f"✅ Downloaded {len(ds)} documents")
    print(f"📋 Columns: {ds.column_names}")
    return ds


# ─────────────────────────────────────────────────────────────
# FILTER: Title-based matching (VERY strict)
# ─────────────────────────────────────────────────────────────

# These must appear in the document TITLE (first 500 chars)
TITLE_KEYWORDS = [
    "bộ luật lao động",
    "luật lao động",
    "luật việc làm",
    "luật an toàn, vệ sinh lao động",
    "luật an toàn vệ sinh lao động",
    "luật bảo hiểm xã hội",
    "luật bảo hiểm y tế",
    "luật công đoàn",
    "hợp đồng lao động",
    "kỷ luật lao động",
    "tranh chấp lao động",
    "quan hệ lao động",
    "tiền lương",
    "an toàn lao động",
    "tai nạn lao động",
    "bảo hiểm thất nghiệp",
    "nghỉ thai sản",
    "thỏa ước lao động",
    "đình công",
]

# Exact law/decree codes — match anywhere in document
EXACT_LAW_CODES = [
    # Luật
    "45/2019/qh14",     # Bộ luật Lao động 2019
    "10/2012/qh13",     # Bộ luật Lao động 2012
    "58/2014/qh13",     # Luật BHXH
    "25/2014/qh13",     # Luật BHYT sửa đổi
    "12/2012/qh13",     # Luật Công đoàn
    "38/2013/qh13",     # Luật Việc làm
    "84/2015/qh13",     # Luật ATVSLĐ
    # Nghị định hướng dẫn BLLĐ 2019
    "145/2020/nđ-cp",   # Hướng dẫn BLLĐ
    "135/2020/nđ-cp",   # Tuổi nghỉ hưu
    "152/2020/nđ-cp",   # Lao động nước ngoài
    "12/2022/nđ-cp",    # Xử phạt vi phạm lao động
    "38/2022/nđ-cp",    # Lương tối thiểu
    "115/2015/nđ-cp",   # Hướng dẫn luật BHXH
    "143/2018/nđ-cp",   # BHXH bắt buộc cho lao động nước ngoài
    "148/2018/nđ-cp",   # Sửa đổi NĐ 05/2015 về lao động
]


def filter_labor_law(ds) -> list:
    """Filter dataset for labor law documents (TITLE-ONLY).

    Only includes documents where:
    1. The TITLE area (first 500 chars) mentions a labor-specific keyword, OR
    2. The document references an exact labor law code number.

    NO fallback to body keyword counting — that caused 254K false positives.

    Args:
        ds: HuggingFace dataset.

    Returns:
        List of filtered document dicts.
    """
    print("🔍 Filtering for Labor Law documents (title-only mode)...")
    labor_docs = []

    for row in tqdm(ds, desc="Filtering"):
        text = row.get("markdown", "")
        if not text:
            continue

        text_lower = text.lower()
        title_area = text_lower[:500]

        # Rule 1: Title area contains labor-specific keyword
        if any(kw in title_area for kw in TITLE_KEYWORDS):
            labor_docs.append({
                "doc_id": row.get("doc_id", 0),
                "markdown": text,
            })
            continue

        # Rule 2: Document references exact labor law code
        if any(code in text_lower for code in EXACT_LAW_CODES):
            labor_docs.append({
                "doc_id": row.get("doc_id", 0),
                "markdown": text,
            })

    print(f"✅ Found {len(labor_docs)} Labor Law documents out of {len(ds)} total")
    return labor_docs


def extract_law_name(markdown_text: str) -> str:
    """Extract the law name/title from the beginning of a document.

    Args:
        markdown_text: Full markdown text of the legal document.

    Returns:
        Extracted law name string.
    """
    # Try to find the law title pattern
    patterns = [
        r"\*\*LUẬT\*\*\s*\n\s*\*\*(.*?)\*\*",
        r"\*\*BỘ LUẬT\*\*\s*\n\s*\*\*(.*?)\*\*",
        r"\*\*NGHỊ ĐỊNH\*\*\s*\n\s*\*\*(.*?)\*\*",
        r"\*\*THÔNG TƯ\*\*\s*\n\s*\*\*(.*?)\*\*",
        r"Luật số:\s*(\S+)",
        r"Nghị định số:\s*(\S+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, markdown_text[:2000])
        if match:
            return match.group(1).strip()[:200]

    # Fallback: use first substantial line
    for line in markdown_text[:1000].split("\n"):
        line = line.strip().strip("*#| ")
        if len(line) > 20 and "---" not in line and "CỘNG HÒA" not in line:
            return line[:200]

    return "Văn bản pháp luật lao động"


def chunk_by_article(markdown_text: str, law_name: str, doc_id: int) -> list:
    """Chunk a legal document by Điều (Article).

    Respects the hierarchical structure: Chương > Mục > Điều > Khoản.
    Each chunk contains one full Điều with its parent Chương/Mục context.

    Args:
        markdown_text: Full markdown text.
        law_name: Name of the law.
        doc_id: Original document ID.

    Returns:
        List of chunk dicts with text and metadata.
    """
    chunks = []

    # Track current chapter and section context
    current_chapter = ""
    current_section = ""

    # Split by Điều pattern
    # Match: **Điều 123. Tên điều**  or  Điều 123. Tên điều
    article_split = re.split(
        r"(?=\*{0,2}Điều\s+\d+[a-z]?\.)",
        markdown_text,
    )

    for part in article_split:
        part = part.strip()
        if not part or len(part) < 30:
            continue

        # Update chapter context
        chap_match = re.search(r"\*{0,2}Chương\s+([IVXLCDM]+|[0-9]+)\*{0,2}\s*\n\s*\*{0,2}(.*?)\*{0,2}", part)
        if chap_match:
            current_chapter = f"Chương {chap_match.group(1)}: {chap_match.group(2).strip()}"

        # Update section context
        sec_match = re.search(r"\*{0,2}Mục\s+(\d+)\*{0,2}\s*\n\s*\*{0,2}(.*?)\*{0,2}", part)
        if sec_match:
            current_section = f"Mục {sec_match.group(1)}: {sec_match.group(2).strip()}"

        # Extract article number and name
        article_match = re.match(
            r"\*{0,2}(Điều\s+\d+[a-z]?\.?\s*[^\n*]*)\*{0,2}",
            part,
        )

        if article_match:
            article_name = article_match.group(1).strip().strip("*")
        else:
            # Not an article chunk, check if it's still useful content
            if len(part) > 200 and any(kw in part.lower() for kw in LABOR_KEYWORDS[:10]):
                article_name = "Phần mở đầu / Quy định chung"
            else:
                continue

        # Build chunk text with context
        context_prefix = ""
        if current_chapter:
            context_prefix += f"[{current_chapter}]\n"
        if current_section:
            context_prefix += f"[{current_section}]\n"
        context_prefix += f"[{law_name}]\n\n"

        chunk_text = context_prefix + part

        # Data versioning metadata
        version_meta = {
            "article": article_name,
            "law_name": law_name,
            "doc_id": str(doc_id),
            "chapter": current_chapter,
            "section": current_section,
            "source": "kiil-lab/vietnamese-law-corpus",
            "type": "law_article",
            "version": time.strftime("%Y-%m-%d"),
            "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # Limit chunk size (if an article is very long)
        if len(chunk_text) > 3000:
            # Split long articles into sub-chunks at Khoản boundaries
            sub_chunks = re.split(r"(?=\n\d+\.\s)", part)
            overlap = 200
            total = len([s for s in sub_chunks if len(s.strip()) >= 50])
            chunk_idx = 0
            prev_tail = ""

            for i, sub in enumerate(sub_chunks):
                sub = sub.strip()
                if len(sub) < 50:
                    continue
                # Add overlap from previous chunk
                sub_with_overlap = prev_tail + sub if prev_tail else sub
                sub_text = context_prefix + sub_with_overlap
                chunk_id = hashlib.md5(sub_text[:300].encode()).hexdigest()
                chunks.append({
                    "id": chunk_id,
                    "text": sub_text[:3000],
                    "metadata": {
                        **version_meta,
                        "sub_part": chunk_idx,
                        "chunk_index": chunk_idx,
                        "total_chunks": total,
                    },
                })
                # Save tail for overlap
                prev_tail = sub[-overlap:] if len(sub) > overlap else sub
                chunk_idx += 1
        else:
            chunk_id = hashlib.md5(chunk_text[:300].encode()).hexdigest()
            chunks.append({
                "id": chunk_id,
                "text": chunk_text,
                "metadata": {
                    **version_meta,
                    "chunk_index": 0,
                    "total_chunks": 1,
                },
            })

    return chunks


# ─────────────────────────────────────────────────────────────
# Source 2: Q&A Dataset (namphan1999)
# ─────────────────────────────────────────────────────────────

def download_qa_dataset():
    """Download the Vietnamese legal Q&A dataset.

    Dataset: namphan1999/data-luat
    Columns: question (str), answer (str), terms (str)
    Size: 2,519 Q&A pairs
    """
    print("\n📥 Downloading namphan1999/data-luat (Q&A dataset)...")
    ds = load_dataset("namphan1999/data-luat", split="train")
    print(f"✅ Downloaded {len(ds)} Q&A pairs")
    return ds


def filter_labor_qa(ds) -> list:
    """Filter Q&A dataset for labor-related questions.

    Args:
        ds: HuggingFace dataset.

    Returns:
        List of filtered Q&A dicts.
    """
    print("🔍 Filtering Q&A for labor-related questions...")
    labor_qa = []

    labor_qa_keywords = [
        "lao động", "hợp đồng lao", "tiền lương", "nghỉ phép",
        "sa thải", "bảo hiểm xã hội", "bhxh", "thai sản",
        "thử việc", "công đoàn", "đình công", "kỷ luật",
        "an toàn lao động", "tai nạn lao động", "nghỉ việc",
        "trợ cấp thôi việc", "lương tối thiểu", "làm thêm giờ",
        "chấm dứt hợp đồng", "luật lao động",
    ]

    for row in ds:
        combined = f"{row.get('question', '')} {row.get('answer', '')} {row.get('terms', '')}".lower()
        if any(kw in combined for kw in labor_qa_keywords):
            labor_qa.append(row)

    print(f"✅ Found {len(labor_qa)} labor-related Q&A out of {len(ds)} total")
    return labor_qa


def chunk_qa(qa_list: list) -> list:
    """Convert Q&A pairs into chunks for embedding.

    Each chunk = "Câu hỏi: ... \n Trả lời: ... \n Căn cứ: ..."

    Args:
        qa_list: List of Q&A dicts.

    Returns:
        List of chunk dicts.
    """
    chunks = []
    for qa in qa_list:
        question = qa.get("question", "").strip()
        answer = qa.get("answer", "").strip()
        terms = qa.get("terms", "").strip()

        if not question or not answer:
            continue

        text = f"Câu hỏi: {question}\n\nTrả lời: {answer}"
        if terms:
            text += f"\n\nCăn cứ pháp lý: {terms}"

        chunk_id = hashlib.md5(text[:300].encode()).hexdigest()
        chunks.append({
            "id": chunk_id,
            "text": text,
            "metadata": {
                "article": terms or "Q&A",
                "law_name": terms or "Tư vấn pháp luật lao động",
                "source": "namphan1999/data-luat",
                "type": "qa_pair",
                "question": question[:200],
            },
        })

    print(f"✅ Created {len(chunks)} Q&A chunks")
    return chunks


# ─────────────────────────────────────────────────────────────
# Common: Deduplicate, Save, Embed, Store
# ─────────────────────────────────────────────────────────────

def deduplicate_chunks(chunks: list) -> list:
    """Remove duplicate chunks by ID.

    Args:
        chunks: List of chunk dicts.

    Returns:
        Deduplicated list.
    """
    seen = set()
    unique = []
    for chunk in chunks:
        if chunk["id"] not in seen:
            seen.add(chunk["id"])
            unique.append(chunk)
    removed = len(chunks) - len(unique)
    if removed:
        print(f"🔄 Removed {removed} duplicate chunks")
    return unique


def save_chunks(chunks: list, filename: str = "labor_law_chunks.jsonl"):
    """Save processed chunks to JSONL file.

    Args:
        chunks: List of chunk dicts.
        filename: Output filename.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / filename

    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    total_size = output_path.stat().st_size / 1024 / 1024
    print(f"💾 Saved {len(chunks)} chunks to {output_path} ({total_size:.1f} MB)")
    return output_path


def embed_and_store(chunks: list):
    """Embed chunks and store in Qdrant.

    Uses local fastembed model — no API limits, no rate limiting needed.

    Args:
        chunks: List of chunk dicts.
    """
    from src.embeddings.embedding_service import VECTOR_SIZE

    print(f"\n🧬 Embedding chunks and storing in Qdrant (local model)...")
    print(f"   Vector size: {VECTOR_SIZE}, Total chunks: {len(chunks)}")

    # Create collection with correct vector size
    create_collection(vector_size=VECTOR_SIZE)

    # Process in batches — local model, no rate limits
    batch_size = 256
    total_batches = (len(chunks) + batch_size - 1) // batch_size
    stored = 0

    for i in tqdm(range(0, len(chunks), batch_size), total=total_batches, desc="Embedding & storing"):
        batch = chunks[i : i + batch_size]

        texts = [c["text"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        try:
            embeddings = embed_texts(texts)

            point_ids = list(range(i, i + len(batch)))

            upsert_documents(
                ids=point_ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            stored += len(batch)

        except Exception as e:
            print(f"\n⚠️ Error on batch {i // batch_size + 1}: {e}")
            print("   Retrying...")
            try:
                embeddings = embed_texts(texts)
                point_ids = list(range(i, i + len(batch)))
                upsert_documents(
                    ids=point_ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas,
                )
                stored += len(batch)
            except Exception as e2:
                print(f"   ❌ Failed: {e2}. Skipping batch.")

    print(f"✅ Stored {stored}/{len(chunks)} vectors in Qdrant")


def load_saved_chunks(filename: str = "labor_law_chunks.jsonl") -> list:
    """Load previously saved chunks from JSONL file.

    Args:
        filename: JSONL filename in PROCESSED_DIR.

    Returns:
        List of chunk dicts, or empty list if file not found.
    """
    filepath = PROCESSED_DIR / filename
    if not filepath.exists():
        return []

    chunks = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))

    print(f"📂 Loaded {len(chunks)} chunks from {filepath}")
    return chunks


def main():
    """Run the full ingestion pipeline.

    Supports resume: if chunks were already processed and saved,
    skips download/filter/chunk and goes straight to embedding.
    """
    print("=" * 60)
    print("🚀 LEGAL DATA INGESTION PIPELINE")
    print("=" * 60)

    # ── Check for saved chunks (resume mode) ──
    all_chunks = load_saved_chunks()

    if all_chunks:
        print(f"\n✅ Found saved chunks! Skipping download & processing.")
        print(f"   (Delete data/processed/labor_law_chunks.jsonl to re-process)")
    else:
        # ── Source 1: Law Corpus ──
        print("\n" + "─" * 40)
        print("📚 Source 1: Vietnamese Law Corpus")
        print("─" * 40)

        ds_corpus = download_law_corpus()
        labor_docs = filter_labor_law(ds_corpus)

        if not labor_docs:
            print("⚠️ No Labor Law documents found in corpus!")
        else:
            print(f"\n✂️ Chunking {len(labor_docs)} documents by Điều (Article)...")
            for doc in tqdm(labor_docs, desc="Chunking"):
                law_name = extract_law_name(doc["markdown"])
                doc_chunks = chunk_by_article(doc["markdown"], law_name, doc["doc_id"])
                all_chunks.extend(doc_chunks)
            print(f"✅ Created {len(all_chunks)} chunks from law corpus")

        # ── Source 2: Q&A Dataset ──
        print("\n" + "─" * 40)
        print("📚 Source 2: Legal Q&A Dataset")
        print("─" * 40)

        ds_qa = download_qa_dataset()
        labor_qa = filter_labor_qa(ds_qa)

        if labor_qa:
            qa_chunks = chunk_qa(labor_qa)
            all_chunks.extend(qa_chunks)

        # ── Deduplicate ──
        all_chunks = deduplicate_chunks(all_chunks)

        if not all_chunks:
            print("❌ No chunks to process!")
            return

        # ── Save to JSONL ──
        save_chunks(all_chunks)

    # ── Stats ──
    print(f"\n📊 Chunk Statistics:")
    type_counts = {}
    for c in all_chunks:
        t = c["metadata"].get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, count in sorted(type_counts.items()):
        print(f"   {t}: {count}")

    law_counts = {}
    for c in all_chunks:
        law = c["metadata"].get("law_name", "unknown")[:60]
        law_counts[law] = law_counts.get(law, 0) + 1
    print(f"\n📜 Top 10 Laws by chunk count:")
    for law, count in sorted(law_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"   {law}: {count} chunks")

    # ── Embed & Store ──
    embed_and_store(all_chunks)

    print("\n" + "=" * 60)
    print("✅ INGESTION COMPLETE!")
    print(f"📊 Total chunks stored: {len(all_chunks)}")
    print("=" * 60)


if __name__ == "__main__":
    main()

