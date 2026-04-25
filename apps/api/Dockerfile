FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN useradd --create-home --uid 10001 structura \
    && mkdir -p /srv/structura \
    && chown -R structura:structura /app /srv/structura

COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY --chown=structura:structura . /app

EXPOSE 8000

USER structura

CMD ["uvicorn", "apps.api.structura_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
