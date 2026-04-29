FROM python:3.11-slim-bookworm

WORKDIR /app

RUN sed -i 's|http://deb.debian.org|https://cdn-fastly.deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# GPU: Install onnxruntime-gpu (CUDA 12, default since v1.19) + ALL CUDA libs
RUN pip install --no-cache-dir --timeout=600 --retries=3 \
    onnxruntime-gpu \
    nvidia-cublas-cu12 \
    nvidia-cuda-runtime-cu12 \
    nvidia-cuda-nvrtc-cu12 \
    nvidia-cudnn-cu12 \
    nvidia-curand-cu12 \
    nvidia-cufft-cu12 \
    nvidia-cusolver-cu12 \
    nvidia-cusparse-cu12 \
    nvidia-nvjitlink-cu12

# Register all NVIDIA libs with ldconfig (more reliable than LD_LIBRARY_PATH)
RUN for dir in /usr/local/lib/python3.11/site-packages/nvidia/*/lib; do \
      echo "$dir" >> /etc/ld.so.conf.d/nvidia.conf; \
    done && ldconfig

# Verify GPU libs are discoverable
RUN ldconfig -p | grep -c cublas && echo "✅ CUDA libs registered"

# Install antiword for .doc file support (separate layer to preserve CUDA cache)
RUN apt-get update && apt-get install -y --no-install-recommends antiword \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
