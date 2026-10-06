FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium \
    && groupadd --gid 10001 qa \
    && useradd --uid 10001 --gid qa --create-home qa \
    && mkdir -p /app/qa-runs \
    && chown -R qa:qa /app/qa-runs /ms-playwright

USER qa

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "autonomous_qa.api:app", "--host", "0.0.0.0", "--port", "8000"]
