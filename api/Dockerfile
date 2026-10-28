FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV FASTEMBED_CACHE_PATH=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}')" \
    && chmod -R a+rX /models

COPY . .

RUN useradd --create-home --uid 10001 app
USER app

# nginx (the only client of this port) sets X-Forwarded-For to the real client address, so the
# per-client rate limit sees visitors, not the proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
