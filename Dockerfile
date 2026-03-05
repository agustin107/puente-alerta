FROM python:3.11-slim

# Instalar dependencias del sistema para OpenCV y ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0t64 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copiar requirements e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descargar modelo YOLO para no descargarlo en cada inicio
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# Copiar código fuente
COPY . .

# Ejecutar
CMD ["python", "main.py"]
