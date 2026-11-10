FROM python:3.12-slim

# Evitar buffers y archivos .pyc
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Puerto para panel web
EXPOSE 5000

CMD ["python", "agente.py"]
