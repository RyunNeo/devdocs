FROM python:3.14-slim AS dependencies

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY apps/api/requirements.lock.txt ./requirements.lock.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir -r requirements.lock.txt

FROM python:3.14-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/uploads \
    && chown 10001:10001 /data/uploads

COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app
COPY --chown=10001:10001 apps/api/app ./app
COPY --chown=10001:10001 apps/api/alembic.ini ./alembic.ini

USER 10001:10001
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
