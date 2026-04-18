# Single Dockerfile for both the agents (main.py) and UI (ui/app.py)
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m textblob.download_corpora && \
    python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"

# v3 removed the RAG stack (ChromaDB + sentence-transformers). Do not re-add the
# embedding download here — the LLM Wiki under data/wiki/ is plain markdown.

COPY . .

RUN mkdir -p /app/data /app/data/wiki /app/data/raw

CMD ["python", "main.py"]
