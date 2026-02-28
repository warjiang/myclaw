FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if needed (e.g. git for skill import)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src ./src

# Install dependencies and the package
RUN pip install --no-cache-dir .

# Create directories for config and skills
RUN mkdir -p /root/.myclaw/skills

# Set entrypoint
ENTRYPOINT ["myclaw"]
CMD ["start"]
