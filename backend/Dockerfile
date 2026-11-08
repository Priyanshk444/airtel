FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/tests/fixtures ./tests/fixtures
COPY data /data
ENV UDYAM_DATA_DIR=/data UDYAM_DB_PATH=/var/udyam/app.sqlite
RUN mkdir -p /var/udyam

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
