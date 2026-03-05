"""
Configuración central del sistema de alerta.
Carga valores desde variables de entorno (.env)
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # YouTube
    YOUTUBE_URL: str = os.getenv(
        "YOUTUBE_URL", "https://www.youtube.com/watch?v=WxqFswgQqUk"
    )

    # Detection
    FRAME_INTERVAL: int = int(os.getenv("FRAME_INTERVAL", "3"))
    DETECTION_CONFIDENCE: float = float(os.getenv("DETECTION_CONFIDENCE", "0.4"))
    ALERT_THRESHOLD_SECONDS: int = int(os.getenv("ALERT_THRESHOLD_SECONDS", "180"))
    ALERT_COOLDOWN_SECONDS: int = int(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))

    # YOLO
    YOLO_MODEL: str = os.getenv("YOLO_MODEL", "yolov8n.pt")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
