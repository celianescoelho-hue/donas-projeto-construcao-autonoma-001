FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Node.js + Yarn and build tools are required so the preview runner can install
# dependencies and launch each project's real FastAPI backend (and any Node tooling).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl git ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g yarn \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Working area for full-stack previews (projects' backends run here).
ENV PREVIEW_DIR=/tmp/donas_previews

EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
