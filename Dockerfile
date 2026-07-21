# syntax=docker/dockerfile:1
FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/Lixiang878/llm-testcase-gen"
LABEL org.opencontainers.image.description="LLM-powered unit-test generator that executes what it generates"

WORKDIR /app

COPY . /app

# Offline core install: numpy only. A real LLM provider (OpenAI/Anthropic/...)
# is OPTIONAL and lazy-imported; the bundled MockProvider runs with zero network.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e . \
    && pip install --no-cache-dir pytest

CMD ["pytest", "-q"]

# Run the generator with the offline mock provider:
#   docker build -t llm-testcase-gen .
#   docker run --rm llm-testcase-gen python -m llm_testcase_gen.cli gen --provider mock
