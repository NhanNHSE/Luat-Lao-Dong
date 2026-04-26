# ⚖️ Chatbot Luật Lao Động Việt Nam

Chatbot tư vấn pháp luật Luật Lao Động Việt Nam, sử dụng kiến trúc **RAG (Retrieval-Augmented Generation)** kết hợp **Gemini AI** để trả lời câu hỏi dựa trên nội dung văn bản luật thực tế.

## 🏗️ Kiến Trúc

```
User → Frontend (Nginx) → Backend (FastAPI) → RAG Pipeline
                                                  ├── Qdrant (Vector DB)
                                                  └── Gemini API (LLM)
```

## 🚀 Cài Đặt & Chạy

### 1. Cấu hình
```bash
cp .env.example .env
# Sửa file .env: thêm GEMINI_API_KEY
```

### 2. Chạy với Docker
```bash
docker-compose up -d --build
```

### 3. Nạp dữ liệu luật
```bash
docker exec -it lawbot-backend python scripts/ingest.py
```

### 4. Truy cập
- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Qdrant UI**: http://localhost:6333/dashboard

## 📦 Tech Stack

- **Backend**: FastAPI + Python 3.11
- **LLM**: Google Gemini 2.5 Flash
- **Vector DB**: Qdrant
- **Database**: PostgreSQL
- **Frontend**: HTML/CSS/JS (Vanilla)
- **Infra**: Docker Compose

## 📋 Tính Năng

- ✅ Chat với AI về Luật Lao Động
- ✅ Streaming response (SSE)
- ✅ Trích dẫn nguồn (Điều luật cụ thể)
- ✅ Đăng ký / Đăng nhập (JWT)
- ✅ Lưu lịch sử chat
- ✅ Giao diện dark mode đẹp
- ✅ Responsive (mobile-friendly)
- ✅ Docker-first deployment
