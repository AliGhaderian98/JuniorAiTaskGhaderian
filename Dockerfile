FROM python:3.12-slim

WORKDIR /app

# Model cache inside the image; no Chroma usage telemetry.
ENV HF_HOME=/app/.cache/huggingface \
    ANONYMIZED_TELEMETRY=False \
    PYTHONUNBUFFERED=1

# Install dependencies first: this layer is reused when only the code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/
COPY data/ data/

# Download the embedding model and build the vector index at build time,
# so the container starts quickly and needs no internet except for OpenAI.
RUN python scripts/build_index.py

# The model is now in the image: don't contact huggingface.co at startup
# (without this, startup without internet took ~150 s because of retries).
ENV HF_HUB_OFFLINE=1

# Run as a non-root user.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# OPENAI_API_KEY is passed at runtime: docker run -e OPENAI_API_KEY=... (never baked into the image)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
