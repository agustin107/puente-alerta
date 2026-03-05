"""
Módulo de captura de frames desde YouTube Live Stream.

Usa yt-dlp para obtener la URL directa del stream y OpenCV
para capturar frames individuales.
"""

import subprocess
import time
import logging
import cv2
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class StreamCapture:
    """Captura frames de un stream de YouTube en vivo."""

    def __init__(self, youtube_url: str):
        self.youtube_url = youtube_url
        self.stream_url: Optional[str] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self._last_url_refresh = 0
        self._url_refresh_interval = 3600  # Refrescar URL cada 1 hora

    def _get_stream_url(self) -> Optional[str]:
        """Obtiene la URL directa del stream usando yt-dlp."""
        try:
            logger.info(f"Obteniendo URL del stream: {self.youtube_url}")
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--get-url",
                    "--format", "best[height<=480]",  # 480p para ahorrar recursos
                    "--no-playlist",
                    self.youtube_url,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout.strip():
                url = result.stdout.strip().split("\n")[0]
                logger.info("URL del stream obtenida exitosamente")
                return url
            else:
                logger.error(f"Error yt-dlp: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("Timeout al obtener URL del stream")
            return None
        except FileNotFoundError:
            logger.error("yt-dlp no encontrado. Instalar con: pip install yt-dlp")
            return None
        except Exception as e:
            logger.error(f"Error inesperado obteniendo stream: {e}")
            return None

    def connect(self) -> bool:
        """Conecta al stream de video."""
        self.stream_url = self._get_stream_url()
        if not self.stream_url:
            return False

        self.cap = cv2.VideoCapture(self.stream_url)
        if not self.cap.isOpened():
            logger.error("No se pudo abrir el stream de video")
            return False

        self._last_url_refresh = time.time()
        logger.info("Conectado al stream exitosamente")
        return True

    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Captura un frame del stream.
        Retorna el frame como numpy array o None si falla.
        """
        # Refrescar URL si pasó mucho tiempo
        if time.time() - self._last_url_refresh > self._url_refresh_interval:
            logger.info("Refrescando URL del stream...")
            self.disconnect()
            if not self.connect():
                return None

        if self.cap is None or not self.cap.isOpened():
            logger.warning("Stream no conectado, intentando reconectar...")
            if not self.connect():
                return None

        ret, frame = self.cap.read()
        if not ret or frame is None:
            logger.warning("No se pudo leer frame, reconectando...")
            self.disconnect()
            time.sleep(5)
            if not self.connect():
                return None
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return None

        return frame

    def disconnect(self):
        """Desconecta del stream."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            logger.info("Desconectado del stream")

    def __del__(self):
        self.disconnect()
