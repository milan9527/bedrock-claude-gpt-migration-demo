FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app
COPY --chown=app:app app.py scenarios.py api_adapters.py openai_adapters.py migration_config.py ./
USER app
ENV HOST=0.0.0.0 PORT=8090 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8090
CMD ["python", "app.py"]
