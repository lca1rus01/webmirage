FROM python:3.12-slim

WORKDIR /app

# Install package first for layer caching (source changes rarely vs deps)
COPY pyproject.toml README.md ./
COPY webmirage ./webmirage
RUN pip install --no-cache-dir --timeout 120 .

# Config lives at ~/.webmirage/config.yaml (mount it read-only)
RUN mkdir -p /root/.webmirage

ENV WEBMIRAGE_TRANSPORT=sse \
    WEBMIRAGE_HOST=0.0.0.0 \
    WEBMIRAGE_PORT=8084

EXPOSE 8084

CMD ["python", "-m", "webmirage"]
