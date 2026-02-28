FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml README.md ./
COPY src ./src

RUN uv pip install --system -e .

RUN mkdir -p /root/.myclaw/skills

ENTRYPOINT ["myclaw"]
CMD ["start"]
