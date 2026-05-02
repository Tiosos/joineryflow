FROM python:3.12-slim
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /code
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .
