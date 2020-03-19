FROM python:3.8-slim

ARG ENVIRONMENT="production"

ENV POETRY_VERSION="1.0.5"
ENV APP_ENVIRONMENT=${ENVIRONMENT}
ENV PYTHONUNBUFFERED=1

RUN pip install "poetry==$POETRY_VERSION"

RUN poetry config virtualenvs.create false

WORKDIR /app/

COPY poetry.lock pyproject.toml ./

COPY ./notion_docs_sync/ ./notion_docs_sync/

RUN if [ "$APP_ENVIRONMENT" = "production" ]; then poetry install --nodev; else poetry install; fi

ENTRYPOINT [ "notion-docs-sync"]
CMD []
