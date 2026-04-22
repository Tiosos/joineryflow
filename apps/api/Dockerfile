FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .
