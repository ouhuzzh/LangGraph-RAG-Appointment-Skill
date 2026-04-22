FROM python:3.13

ENV PYTHONUNBUFFERED=1
ENV OLLAMA_HOST=0.0.0.0:11434
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860
ENV OLLAMA_HOME=/home/user/.ollama

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    zstd \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://ollama.com/install.sh | sh

RUN useradd -m -u 1000 user
USER user

ENV PATH="/home/user/.local/bin:$PATH"
WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY --chown=user . .

USER root
COPY <<EOF /app/start.sh
#!/bin/bash
set -e

ollama serve &
echo "Waiting for Ollama..."
until curl -s http://localhost:11434 >/dev/null; do
  sleep 1
done

ollama pull qwen3:4b-instruct-2507-q4_K_M || true

cd project
python app.py
EOF

RUN chmod +x /app/start.sh && chown user:user /app/start.sh

USER user
EXPOSE 7860
CMD ["/app/start.sh"]