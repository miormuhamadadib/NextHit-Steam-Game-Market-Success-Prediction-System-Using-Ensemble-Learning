FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

# Increased timeout for large packages
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PORT=10000
EXPOSE 10000

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]