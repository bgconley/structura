FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libsm6 \
        libx11-6 \
        libxcb1 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 structura \
    && mkdir -p /srv/structura \
    && chown -R structura:structura /app /srv/structura

COPY apps/api/requirements.txt /tmp/api-requirements.txt
COPY workers/docling/requirements.txt /tmp/docling-requirements.txt
RUN pip install --no-cache-dir \
    -r /tmp/api-requirements.txt \
    -r /tmp/docling-requirements.txt

COPY --chown=structura:structura . /app

USER structura

CMD ["python", "-m", "workers.docling.worker", "--worker", "worker-docling", "--health-port", "8203"]
