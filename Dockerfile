FROM python:3.10-slim
LABEL maintainer="kanst9@ya.ru"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    postgresql-client

ENV VENV_PATH=/opt/venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
ENV PATH="$VENV_PATH/bin:$PATH"
RUN python -m venv $VENV_PATH && \
    useradd -ms /bin/sh app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot/
COPY main.py .
COPY migrations ./migrations/
COPY alembic.ini .

RUN mkdir storage && \
    chown app:app storage

USER app

# CMD alembic upgrade head && python3 main.py
