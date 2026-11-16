FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends adb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt app.py ./
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000 8001
CMD ["sh", "-c", "uvicorn app:api --host 0.0.0.0 --port 8000 & uvicorn app:mcp_app --host 0.0.0.0 --port 8001 & wait"]
