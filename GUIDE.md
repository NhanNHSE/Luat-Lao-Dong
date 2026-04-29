# 📖 HƯỚNG DẪN CHI TIẾT — Chatbot Luật Lao Động Việt Nam

## Mục lục

- [1. Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
- [2. Kiến trúc](#2-kiến-trúc)
- [3. Yêu cầu hệ thống](#3-yêu-cầu-hệ-thống)
- [4. Cài đặt & Khởi chạy](#4-cài-đặt--khởi-chạy)
- [5. Cấu hình](#5-cấu-hình)
- [6. Pipeline dữ liệu (Ingestion)](#6-pipeline-dữ-liệu-ingestion)
- [7. RAG Pipeline](#7-rag-pipeline)
- [8. API Reference](#8-api-reference)
- [9. Frontend](#9-frontend)
- [10. GPU & CUDA](#10-gpu--cuda)
- [11. Xử lý sự cố](#11-xử-lý-sự-cố)
- [12. Cấu trúc thư mục](#12-cấu-trúc-thư-mục)

---

## 1. Tổng quan hệ thống

Chatbot tư vấn Luật Lao Động Việt Nam sử dụng kiến trúc **RAG (Retrieval-Augmented Generation)**:

1. **Embedding** câu hỏi của user thành vector (GPU, local model)
2. **Tìm kiếm** các điều luật liên quan trong Qdrant (vector database)
3. **Sinh câu trả lời** bằng Gemini LLM với context từ điều luật
4. **Stream** kết quả realtime về frontend qua SSE

### Tech Stack

| Layer | Công nghệ |
|-------|-----------|
| **LLM** | Google Gemini 2.5 Flash |
| **Embedding** | `paraphrase-multilingual-MiniLM-L12-v2` (384 dims, GPU) |
| **Vector DB** | Qdrant v1.13 |
| **Backend** | FastAPI + Python 3.11 |
| **Database** | PostgreSQL 16 |
| **Frontend** | Vanilla HTML/CSS/JS + Nginx |
| **Infra** | Docker Compose + NVIDIA GPU |

---

## 2. Kiến trúc

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│   Browser    │────▶│  Nginx (port 3000)                       │
│  (Frontend)  │     │  - Static files (HTML/CSS/JS)            │
└─────────────┘     │  - Proxy /api/* → backend:8000            │
                    └────────────────┬─────────────────────────┘
                                     │
                    ┌────────────────▼─────────────────────────┐
                    │  FastAPI Backend (port 8000)              │
                    │  ┌─────────┐ ┌─────────┐ ┌────────────┐ │
                    │  │  Auth   │ │  Chat   │ │  Contract  │ │
                    │  │  API    │ │  API    │ │  API       │ │
                    │  └────┬────┘ └────┬────┘ └─────┬──────┘ │
                    │       │           │             │        │
                    │  ┌────▼───────────▼─────────────▼──────┐ │
                    │  │         RAG Chain                    │ │
                    │  │  embed_query → search → LLM generate│ │
                    │  └──────┬─────────────┬────────────────┘ │
                    └─────────┼─────────────┼──────────────────┘
                              │             │
                    ┌─────────▼───┐   ┌─────▼────────┐
                    │   Qdrant    │   │  PostgreSQL   │
                    │  (vectors)  │   │  (users/chat) │
                    │  52K chunks │   │               │
                    └─────────────┘   └───────────────┘
```

### Luồng xử lý câu hỏi

```
User gõ câu hỏi
    │
    ▼
POST /api/chat/stream (SSE)
    │
    ├─ 1. Save user message to PostgreSQL
    │
    ├─ 2. embed_query(question) → vector 384 dims  [GPU]
    │
    ├─ 3. Qdrant search(vector, top_k=8) → 8 điều luật
    │      ← SSE: {type: "timing", retrieval_time: 0.5}
    │
    ├─ 4. build_rag_prompt(question, documents, history)
    │
    ├─ 5. Gemini generate_content_stream(prompt)
    │      ← SSE: {type: "chunk", content: "..."}  (nhiều lần)
    │
    ├─ 6. Save assistant message + sources to PostgreSQL
    │      ← SSE: {type: "sources", sources: [...]}
    │
    ├─ 7. Auto-generate conversation title (nếu mới)
    │      ← SSE: {type: "title_update", title: "..."}
    │
    └─ 8. Done
           ← SSE: {type: "done", total_time: 5.2}
```

---

## 3. Yêu cầu hệ thống

### Bắt buộc
- **Docker Desktop** với WSL2 backend
- **NVIDIA GPU** + Driver ≥ 525.x (hỗ trợ CUDA 12)
- **NVIDIA Container Toolkit** (`nvidia-docker2`)
- **RAM**: ≥ 8GB
- **Disk**: ≥ 10GB (Docker images + Qdrant data)

### Kiểm tra GPU
```bash
# Host driver
nvidia-smi

# Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### API Key
- **Gemini API Key** từ [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- ⚠️ Phải **link Billing Account** (miễn phí) để kích hoạt quota

---

## 4. Cài đặt & Khởi chạy

### Bước 1: Clone & cấu hình

```bash
git clone <repo-url>
cd the-first

# Tạo file .env
cp .env.example .env
# Sửa GEMINI_API_KEY trong .env
```

### Bước 2: Khởi chạy

```bash
# Build và chạy tất cả services
docker compose up -d --build

# Kiểm tra containers
docker compose ps
```

### Bước 3: Ingest dữ liệu

```bash
# Chạy pipeline nạp dữ liệu luật lao động
docker exec -it lawbot-backend python scripts/ingest.py
```

### Bước 4: Truy cập

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API Docs | http://localhost:8000/docs |
| Qdrant UI | http://localhost:6333/dashboard |


# Backend log (realtime)
docker logs lawbot-backend -f --tail 50
# Frontend log (nginx)
docker logs lawbot-frontend -f --tail 50
# Tất cả containers
docker compose logs -f --tail 30
# Chỉ xem lỗi
docker logs lawbot-backend -f 2>&1 | grep -i "error\|exception\|failed"


### Bước 5: Sử dụng

1. Đăng ký tài khoản tại trang login
2. Gõ câu hỏi về luật lao động
3. Xem câu trả lời stream realtime + trích dẫn nguồn

---

## 5. Cấu hình

### File `.env`

```env
# Gemini API (bắt buộc)
GEMINI_API_KEY=AIzaSy...

# PostgreSQL
POSTGRES_USER=lawbot
POSTGRES_PASSWORD=lawbot_secret_2026
POSTGRES_DB=lawbot_db
DATABASE_URL=postgresql://lawbot:lawbot_secret_2026@postgres:5432/lawbot_db

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# JWT Auth
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=1440

# App
APP_NAME=Chatbot Luật Lao Động
DEBUG=true
```

### Config Python (`src/core/config.py`)

| Setting | Default | Mô tả |
|---------|---------|--------|
| `embedding_model` | `paraphrase-multilingual-MiniLM-L12-v2` | Model embedding local |
| `llm_model` | `gemini-2.5-flash` | Model Gemini cho LLM |
| `retrieval_top_k` | `8` | Số documents retrieve |
| `chunk_size` | `1000` | Kích thước chunk |
| `chunk_overlap` | `200` | Overlap giữa chunks |

---

## 6. Pipeline dữ liệu (Ingestion)

### Nguồn dữ liệu

| Dataset | HuggingFace ID | Mô tả |
|---------|---------------|--------|
| Vietnamese Law Corpus | `kiil-lab/vietnamese-law-corpus` | 215K+ văn bản luật VN (markdown) |
| Legal Q&A | `namphan1999/data-luat` | 2.5K cặp hỏi-đáp pháp luật |

### Pipeline Steps

```
Download (HuggingFace)
    │
    ▼
Filter (title-based keywords) → ~3,000 docs luật lao động
    │
    ▼
Chunk by "Điều" (Article) → ~86K chunks
    │
    ▼
Merge Q&A pairs → +58 chunks
    │
    ▼
Deduplicate (MD5 hash) → ~52K unique chunks
    │
    ▼
Embed (GPU, batch=256) → vectors 384 dims
    │
    ▼
Store in Qdrant → collection "labor_law"
```

### Chạy lại ingestion

```bash
# Xóa collection cũ và ingest lại
docker exec lawbot-backend python -c "
from qdrant_client import QdrantClient
c = QdrantClient(host='qdrant', port=6333)
c.delete_collection('labor_law')
print('Deleted')
"

docker exec -it lawbot-backend python scripts/ingest.py
```

### Kiểm tra dữ liệu

```bash
# Số vectors trong Qdrant
docker exec lawbot-backend python -c "
from src.embeddings.vector_store import get_collection_info
print(get_collection_info())
"
# Expected: {'name': 'labor_law', 'points_count': 52015}
```

---

## 7. RAG Pipeline

### Flow chi tiết

```python
# 1. Embed query (GPU)
query_embedding = embed_query("Thời gian thử việc?")  # → [0.1, -0.3, ...] 384 dims

# 2. Search Qdrant
documents = search(query_embedding, top_k=8)
# → [{"text": "Điều 25...", "metadata": {"article": "Điều 25", "law_name": "Bộ luật Lao động"}}]

# 3. Build prompt
prompt = build_rag_prompt(question, documents, history)
# → System prompt + Context (8 điều luật) + Chat history + Question

# 4. Generate (streaming)
for chunk in gemini.generate_content_stream(prompt):
    yield chunk.text  # → SSE to frontend
```

### System Prompt

```
Bạn là một chuyên gia tư vấn pháp luật Việt Nam, chuyên về Luật Lao Động.
Quy tắc:
1. Chỉ trả lời dựa trên ngữ cảnh
2. Trích dẫn cụ thể: số Điều, Khoản, tên luật
3. Giải thích dễ hiểu cho người không chuyên
4. Trả lời bằng tiếng Việt, format Markdown
```

### Caching

- **TTLCache**: 500 entries, TTL = 1 giờ
- Cache key = MD5(question + context)
- Chỉ cache câu hỏi đầu tiên (không có history)

---

## 8. API Reference

### Authentication

#### POST `/api/auth/register`
```json
// Request
{ "username": "user1", "email": "user@email.com", "password": "123456" }

// Response 201
{ "access_token": "eyJ...", "token_type": "bearer", "user": {...} }
```

#### POST `/api/auth/login`
```json
// Request
{ "username": "user1", "password": "123456" }

// Response 200
{ "access_token": "eyJ...", "token_type": "bearer", "user": {...} }
```

### Chat

#### POST `/api/chat/stream`
SSE streaming endpoint. Yêu cầu `Authorization: Bearer <token>`.

```json
// Request
{ "message": "Thời gian thử việc tối đa?", "conversation_id": null }
```

SSE Events:
```
data: {"type": "meta", "conversation_id": "uuid"}
data: {"type": "timing", "retrieval_time": 0.45}
data: {"type": "chunk", "content": "Theo Điều 25..."}
data: {"type": "chunk", "content": " Bộ luật Lao động..."}
data: {"type": "sources", "sources": [{"article": "Điều 25", "law_name": "BLLĐ"}]}
data: {"type": "title_update", "title": "Thử việc tối đa"}
data: {"type": "done", "total_time": 5.2}
```

#### GET `/api/chat/conversations`
Danh sách hội thoại. Hỗ trợ `?search=keyword`.

#### GET `/api/chat/conversations/{id}`
Chi tiết hội thoại + messages.

#### DELETE `/api/chat/conversations/{id}`
Xóa hội thoại.

### Contract Analysis

#### POST `/api/contract/analyze`
Upload file hợp đồng để phân tích. Multipart form data.

Hỗ trợ: PDF, DOCX, PNG, JPG, WEBP, BMP, TIFF (max 20MB).
PDF scan và ảnh sẽ được OCR tự động bằng Gemini Vision.

#### GET `/api/contract/supported-formats`
Danh sách format được hỗ trợ.

### Health Check

#### GET `/api/health`
```json
{
  "status": "healthy",
  "app": "Chatbot Luật Lao Động",
  "vector_store": { "name": "labor_law", "points_count": 52015 },
  "cache": { "current_size": 0, "max_size": 500, "ttl_seconds": 3600 }
}
```

### Rate Limits

| Endpoint | Limit |
|----------|-------|
| `/api/auth/register` | 5/phút |
| `/api/auth/login` | 10/phút |
| `/api/chat/stream` | 10/phút |
| `/api/contract/analyze` | 5/phút |

---

## 9. Frontend

### Tính năng UI

- ✅ **Dark theme** glassmorphism
- ✅ **SSE streaming** — hiển thị từng ký tự realtime
- ✅ **Markdown rendering** (marked.js) — bảng, code, heading
- ✅ **Source citations** — badge trích dẫn điều luật
- ✅ **Timing badge** — hiển thị thời gian tìm kiếm + tổng thời gian
- ✅ **Sidebar** — danh sách hội thoại, tìm kiếm, xóa
- ✅ **Auto-title** — tự đặt tên hội thoại
- ✅ **File upload** — tải hợp đồng để phân tích
- ✅ **Responsive** — mobile-friendly
- ✅ **Suggestion chips** — câu hỏi gợi ý

### Cấu trúc JS

| File | Chức năng |
|------|-----------|
| `api.js` | HTTP client, auth token, SSE streaming |
| `auth.js` | Login/Register forms |
| `chat.js` | Chat UI, streaming, conversation management |
| `toast.js` | Toast notifications |
| `app.js` | App initialization, routing |

---

## 10. GPU & CUDA

### Dockerfile Strategy

```dockerfile
# Base image
FROM python:3.11-slim-bookworm

# Install CUDA libs via pip (không cần CUDA toolkit trên host)
RUN pip install onnxruntime-gpu nvidia-cublas-cu12 nvidia-cudnn-cu12 ...

# Register libs with system linker (quan trọng!)
RUN for dir in /usr/local/lib/python3.11/site-packages/nvidia/*/lib; do
      echo "$dir" >> /etc/ld.so.conf.d/nvidia.conf;
    done && ldconfig
```

**Tại sao dùng `ldconfig` thay vì `LD_LIBRARY_PATH`?**
- `LD_LIBRARY_PATH` có thể bị override hoặc format sai
- `ldconfig` ghi vào system dynamic linker cache → đáng tin hơn
- ONNX Runtime tìm `libcublasLt.so.12` qua system linker

### Kiểm tra GPU trong container

```bash
# ONNX Runtime device
docker exec lawbot-backend python -c "
import onnxruntime
print('Device:', onnxruntime.get_device())
print('Providers:', onnxruntime.get_available_providers())
"

# Test embedding
docker exec lawbot-backend python -c "
from src.embeddings.embedding_service import embed_query
v = embed_query('test')
print(f'Vector size: {len(v)}')
"
```

### Docker Compose GPU Config

```yaml
backend:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

---

## 11. Xử lý sự cố

### ❌ Gemini API 429 RESOURCE_EXHAUSTED

**Nguyên nhân:** Hết quota free tier hoặc chưa link billing.

**Giải pháp:**
1. Vào [console.cloud.google.com/billing](https://console.cloud.google.com/billing)
2. Link billing account vào project
3. Google không charge tiền cho free tier (1,500 req/ngày)

### ❌ Gemini API 404 NOT_FOUND

**Nguyên nhân:** Model không khả dụng cho account mới.

**Giải pháp:**
```bash
# List available models
docker exec lawbot-backend python -c "
from google import genai
from src.core.config import get_settings
client = genai.Client(api_key=get_settings().gemini_api_key)
for m in client.models.list():
    if 'flash' in m.name.lower():
        print(m.name)
"
```
Chọn model available và update `config.py`.

### ❌ SSL/Connection Error trong Docker

**Nguyên nhân:** VPN chặn Docker container traffic.

**Giải pháp:** Tắt VPN hoặc cấu hình Docker network mode.

### ❌ `libcublasLt.so.12` not found

**Nguyên nhân:** CUDA libs chưa registered.

**Giải pháp:** Rebuild Docker image:
```bash
docker compose up -d --build backend
```

### ❌ `email-validator is not installed`

**Nguyên nhân:** Thiếu dependency.

**Giải pháp:** Đã thêm `email-validator` vào `requirements.txt`. Rebuild:
```bash
docker compose up -d --build backend
```

### ❌ slowapi `parameter request must be starlette.requests.Request`

**Nguyên nhân:** Tên parameter `request` bị conflict giữa Starlette Request và Pydantic model.

**Giải pháp:** Đổi tên parameter — Starlette Request phải tên `request`, Pydantic model đổi thành `chat_req`.

---

## 12. Cấu trúc thư mục

```
the-first/
├── .env                          # Environment variables
├── docker-compose.yml            # Docker orchestration
├── GUIDE.md                      # This file
│
├── backend/
│   ├── Dockerfile                # Python + CUDA GPU image
│   ├── requirements.txt          # Python dependencies
│   │
│   ├── scripts/
│   │   └── ingest.py             # Data ingestion pipeline
│   │
│   ├── src/
│   │   ├── api/
│   │   │   ├── main.py           # FastAPI app entry point
│   │   │   ├── auth.py           # Register/Login endpoints
│   │   │   ├── chat.py           # Chat streaming endpoint
│   │   │   ├── contract.py       # Contract analysis endpoint
│   │   │   ├── deps.py           # Dependency injection
│   │   │   └── schemas.py        # Pydantic request/response models
│   │   │
│   │   ├── core/
│   │   │   ├── config.py         # Settings (pydantic-settings)
│   │   │   ├── database.py       # SQLAlchemy engine
│   │   │   ├── security.py       # JWT + password hashing
│   │   │   ├── cache.py          # TTLCache for responses
│   │   │   └── logging.py        # Structured logging (structlog)
│   │   │
│   │   ├── database/
│   │   │   └── models.py         # User, Conversation, Message
│   │   │
│   │   ├── embeddings/
│   │   │   ├── embedding_service.py  # Local embedding (GPU/CPU)
│   │   │   └── vector_store.py       # Qdrant CRUD operations
│   │   │
│   │   ├── rag/
│   │   │   ├── chain.py          # RAG: retrieve → prompt → generate
│   │   │   └── prompts.py        # System prompt + templates
│   │   │
│   │   └── services/
│   │       ├── document_processor.py  # PDF/DOCX/Image text extraction
│   │       └── contract_analyzer.py   # Contract analysis with RAG
│   │
│   └── data/
│       └── processed/            # Cached ingested chunks
│
└── frontend/
    ├── Dockerfile                # Nginx static server
    ├── nginx.conf                # Reverse proxy config
    ├── index.html                # Single page app
    ├── css/
    │   └── style.css             # Dark theme design system
    └── js/
        ├── api.js                # API client + auth
        ├── auth.js               # Login/Register UI
        ├── chat.js               # Chat UI + streaming
        ├── toast.js              # Notifications
        └── app.js                # App init
```

---

## Ghi chú phát triển

### Thêm dữ liệu mới

1. Thêm dataset vào `scripts/ingest.py`
2. Thêm keywords filter nếu cần
3. Chạy lại ingestion (xóa collection cũ trước)

### Đổi model embedding

1. Update `MODEL_NAME` trong `embedding_service.py`
2. Update `VECTOR_SIZE` tương ứng
3. **Phải ingest lại toàn bộ** (vector dimensions thay đổi)

### Đổi model LLM

1. Update `llm_model` trong `config.py`
2. Hoặc set `LLM_MODEL` trong `.env`
3. Không cần ingest lại

### Production checklist

- [ ] Đổi `JWT_SECRET_KEY` thành random string dài
- [ ] Set `DEBUG=false`
- [ ] Set `POSTGRES_PASSWORD` mạnh
- [ ] Cấu hình CORS origins cụ thể (không dùng `*`)
- [ ] Set up budget alert cho Gemini API
- [ ] Backup Qdrant data volume
- [ ] Enable HTTPS (Nginx + Let's Encrypt)
