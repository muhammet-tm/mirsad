# Mirsad public demo, built by Hugging Face Spaces (Docker SDK). scripts/deploy_space.py assembles the
# build folder from an allow-list of repository files; .env and the raw data are never in it. API keys
# reach the container only as Space secrets, at run time.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MIRSAD_PUBLIC=1 \
    MIRSAD_SCHEDULE=1 \
    MIRSAD_SANDBOX_URL=off \
    MIRSAD_CERTSTREAM=off

# Noto fonts give the PDF reports proper Arabic text.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-deploy.txt ./
RUN pip install -r requirements.txt -r requirements-deploy.txt \
    && python -m playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*

# Spaces run the container as user 1000.
RUN useradd --create-home --uid 1000 user
COPY --chown=user:user . /app
RUN mkdir -p /app/data/captures && chown -R user:user /app/data
USER user

EXPOSE 7860
CMD ["python", "deploy/start.py"]
