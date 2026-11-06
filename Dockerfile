# Image of the Digital Library and Booking System: the API and the web pages (DLBS-42).
#   docker compose up --build        starts it with PostgreSQL (see docker-compose.yml)
# Settings come from environment variables; see .env.example.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY data/books.csv data/books_sample.csv ./data/

# Run as a normal user. It owns /app so that a local SQLite file can be created there.
RUN useradd --create-home --uid 1000 app && chown app /app
USER app

ENV PORT=8000
EXPOSE 8000
CMD ["python", "-m", "scripts.start"]
