# Conductor production image. ARM64 for AWS Graviton / AgentCore Runtime.
FROM public.ecr.aws/docker/library/python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY conductor ./conductor
# The built React SPA (web/dist) is served at /app; without it the service
# falls back to the vanilla pages.
COPY web/dist ./web/dist

# The control loop runs agents that write files and execute checks. Inside the
# runtime the task role is the correct identity, so ambient credentials are used.
ENV CONDUCTOR_AWS_PROFILE="" \
    CONDUCTOR_HOST="0.0.0.0" \
    CONDUCTOR_PORT="8080" \
    CONDUCTOR_PROVIDER="bedrock" \
    PYTHONUNBUFFERED="1"

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/api/health')"

CMD ["uvicorn", "conductor.asgi:app", "--host", "0.0.0.0", "--port", "8080"]
