# Puente Alerta - Guía de Configuración

Sistema de alerta temprana para el Puente Chaco-Corrientes.
Detecta personas inmóviles en zonas de riesgo y envía alertas a Telegram.

## Estructura del Proyecto

```
puente-alerta/
├── main.py                  # Pipeline principal
├── config/
│   ├── settings.py          # Configuración desde .env
│   └── __init__.py
├── modules/
│   ├── stream_capture.py    # Captura de YouTube Live
│   ├── person_detector.py   # Detección con YOLOv8
│   ├── zone_monitor.py      # Zonas de riesgo + tracking
│   └── telegram_alert.py    # Alertas a Telegram
├── requirements.txt
├── Dockerfile
├── railway.toml             # Config para Railway
├── .env.example
└── .gitignore
```

## Paso 1: Crear Bot de Telegram

1. Abrir Telegram y buscar `@BotFather`
2. Enviar `/newbot`
3. Elegir un nombre (ej: "Alerta Puente Chaco")
4. Elegir un username (ej: `puente_chaco_alerta_bot`)
5. Copiar el **token** que te da BotFather
6. Crear un grupo de Telegram para los voluntarios
7. Agregar el bot al grupo
8. Enviar cualquier mensaje al grupo
9. Visitar: `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
10. Buscar el `"chat": {"id": -XXXXXXXXX}` — ese es tu CHAT_ID (es negativo para grupos)

## Paso 2: Configuración Local (para probar)

```bash
# Clonar el repo
git clone <tu-repo>
cd puente-alerta

# Crear archivo .env
cp .env.example .env

# Editar .env con tus valores
# TELEGRAM_BOT_TOKEN=<tu token de BotFather>
# TELEGRAM_CHAT_ID=<tu chat id del grupo>

# Instalar dependencias
pip install -r requirements.txt

# Probar conexión con Telegram
python main.py --test-telegram

# Modo calibración (captura screenshots para definir zonas)
python main.py --calibrate

# Ejecutar el sistema
python main.py
```

## Paso 3: Calibrar Zonas de Riesgo

Este es el paso más importante. Las zonas por defecto son genéricas.

1. Ejecutar `python main.py --calibrate`
2. Se guardan screenshots en `calibration_screenshots/` con una grilla de porcentajes
3. Mirar las imágenes e identificar dónde están las barandas/bordes del puente
4. Editar `modules/zone_monitor.py` → método `_setup_default_zones()`
5. Ajustar las coordenadas en porcentajes según lo que ves en la grilla

Ejemplo: si la baranda está entre el 70% y 85% vertical de la imagen:
```python
RiskZone(
    name="baranda_sur",
    x1_pct=0.05, y1_pct=0.70,
    x2_pct=0.95, y2_pct=0.85,
    severity="high"
)
```

## Paso 4: Deploy en Railway

1. Crear cuenta en [railway.app](https://railway.app)
2. Crear nuevo proyecto → "Deploy from GitHub repo"
3. Conectar tu repositorio de GitHub
4. En el proyecto de Railway, ir a **Variables** y agregar:
   - `TELEGRAM_BOT_TOKEN` = tu token
   - `TELEGRAM_CHAT_ID` = tu chat id
   - `YOUTUBE_URL` = https://www.youtube.com/watch?v=WxqFswgQqUk
   - `FRAME_INTERVAL` = 3
   - `DETECTION_CONFIDENCE` = 0.4
   - `ALERT_THRESHOLD_SECONDS` = 180
   - `ALERT_COOLDOWN_SECONDS` = 300
   - `YOLO_MODEL` = yolov8n.pt
5. Railway detectará el Dockerfile automáticamente y hará deploy
6. El sistema empezará a correr y enviará un mensaje al grupo de Telegram

## Parámetros Ajustables

| Variable | Default | Descripción |
|----------|---------|-------------|
| `FRAME_INTERVAL` | 3 | Segundos entre capturas de frame |
| `DETECTION_CONFIDENCE` | 0.4 | Confianza mínima YOLO (0.0-1.0). Bajar = más detecciones pero más falsos positivos |
| `ALERT_THRESHOLD_SECONDS` | 180 | Segundos que una persona debe estar inmóvil antes de alertar (3 min) |
| `ALERT_COOLDOWN_SECONDS` | 300 | Segundos mínimos entre alertas (5 min) para evitar spam |
| `YOLO_MODEL` | yolov8n.pt | Modelo YOLO. `n`=nano (rápido), `s`=small (mejor detección, más lento) |

## Ajuste Recomendado para Empezar

Empezar con estos valores conservadores:
- `ALERT_THRESHOLD_SECONDS=300` (5 minutos) — para reducir falsos positivos al inicio
- `DETECTION_CONFIDENCE=0.4` — balance razonable
- `ALERT_COOLDOWN_SECONDS=600` (10 minutos) — para no saturar el grupo

A medida que calibren las zonas y entiendan los patrones, pueden ir bajando el threshold.

## Cómo Funciona

1. **Captura**: Extrae un frame del livestream de YouTube cada N segundos
2. **Detección**: YOLOv8 identifica personas en el frame
3. **Tracking**: Asocia personas entre frames por proximidad
4. **Zonas**: Verifica si alguna persona está en zona de riesgo
5. **Timer**: Si una persona está inmóvil en zona de riesgo por más de X minutos → alerta
6. **Alerta**: Envía foto anotada + info al grupo de Telegram
7. **Cooldown**: Espera Y minutos antes de poder enviar otra alerta

## Solución de Problemas

**El stream no conecta:**
- Verificar que el livestream de YouTube está activo
- YouTube puede bloquear yt-dlp temporalmente; esperar unos minutos
- Verificar que yt-dlp está actualizado: `pip install -U yt-dlp`

**No detecta personas:**
- Verificar resolución del stream (480p mínimo)
- Bajar `DETECTION_CONFIDENCE` a 0.3
- Las personas muy lejanas o pequeñas pueden no detectarse

**Muchos falsos positivos:**
- Subir `ALERT_THRESHOLD_SECONDS`
- Ajustar las zonas de riesgo (calibración)
- Subir `DETECTION_CONFIDENCE` a 0.5

**Error de Telegram:**
- Verificar token y chat_id
- Asegurarse de que el bot está en el grupo
- Ejecutar `python main.py --test-telegram`
