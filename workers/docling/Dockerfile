FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

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
