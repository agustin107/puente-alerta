"""
Módulo de alertas via Telegram.

Envía alertas con imágenes anotadas al grupo de Telegram
cuando se detecta una situación de riesgo.
"""

import io
import time
import logging
import asyncio
import cv2
import numpy as np
from typing import Optional, List
from telegram import Bot
from telegram.constants import ParseMode
from modules.person_detector import Detection
from modules.zone_monitor import TrackedPerson

logger = logging.getLogger(__name__)


class TelegramAlert:
    """Envía alertas al grupo de Telegram."""

    def __init__(self, bot_token: str, chat_id: str, cooldown_seconds: int = 300):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.cooldown = cooldown_seconds
        self._last_alert_time: float = 0
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Obtiene o crea un event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_event_loop()
                if self._loop.is_closed():
                    raise RuntimeError
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _annotate_frame(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        alert_persons: List[TrackedPerson],
    ) -> np.ndarray:
        """
        Dibuja anotaciones sobre el frame para la alerta.
        - Rectángulos verdes: personas detectadas normales
        - Rectángulos rojos: personas en alerta
        """
        annotated = frame.copy()
        alert_centers = {
            (p.center_x, p.center_y) for p in alert_persons
        }

        for det in detections:
            is_alert = any(
                abs(det.center_x - cx) < 50 and abs(det.center_y - cy) < 50
                for cx, cy in alert_centers
            )

            if is_alert:
                color = (0, 0, 255)  # Rojo
                thickness = 3
                label = "⚠ ALERTA"
            else:
                color = (0, 255, 0)  # Verde
                thickness = 2
                label = "Persona"

            # Dibujar bounding box
            cv2.rectangle(
                annotated,
                (det.x1, det.y1),
                (det.x2, det.y2),
                color,
                thickness,
            )

            # Etiqueta
            cv2.putText(
                annotated,
                f"{label} ({det.confidence:.0%})",
                (det.x1, det.y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )

        # Timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            annotated,
            timestamp,
            (10, annotated.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

        return annotated

    def _frame_to_bytes(self, frame: np.ndarray) -> bytes:
        """Convierte un frame OpenCV a bytes JPEG."""
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buffer.tobytes()

    def can_send_alert(self) -> bool:
        """Verifica si pasó suficiente tiempo desde la última alerta."""
        return time.time() - self._last_alert_time >= self.cooldown

    def send_alert(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        alert_persons: List[TrackedPerson],
    ) -> bool:
        """
        Envía una alerta al grupo de Telegram.

        Args:
            frame: Frame actual del video
            detections: Todas las detecciones en el frame
            alert_persons: Personas que dispararon la alerta

        Returns:
            True si la alerta se envió correctamente
        """
        if not self.can_send_alert():
            remaining = self.cooldown - (time.time() - self._last_alert_time)
            logger.info(
                f"Cooldown activo, próxima alerta en {remaining:.0f}s"
            )
            return False

        try:
            # Anotar frame
            annotated = self._annotate_frame(frame, detections, alert_persons)
            image_bytes = self._frame_to_bytes(annotated)

            # Construir mensaje
            zones = set()
            max_time = 0
            for p in alert_persons:
                if p.in_risk_zone:
                    zones.add(p.in_risk_zone)
                max_time = max(max_time, p.time_in_zone)

            zone_str = ", ".join(zones) if zones else "zona de riesgo"
            minutes = int(max_time // 60)
            seconds = int(max_time % 60)

            message = (
                f"🚨 *ALERTA PUENTE CHACO-CORRIENTES*\n\n"
                f"Se detectó una persona inmóvil en *{zone_str}* "
                f"durante *{minutes}m {seconds}s*.\n\n"
                f"👥 Personas en zona de riesgo: {len(alert_persons)}\n"
                f"📍 Zona: {zone_str}\n"
                f"⏱ Tiempo inmóvil: {minutes}m {seconds}s\n\n"
                f"⚠️ _Por favor verificar visualmente. "
                f"Puede ser un falso positivo._"
            )

            # Enviar
            loop = self._get_loop()
            loop.run_until_complete(
                self.bot.send_photo(
                    chat_id=self.chat_id,
                    photo=image_bytes,
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN,
                )
            )

            self._last_alert_time = time.time()
            logger.info(f"Alerta enviada al grupo de Telegram")

            # Marcar personas como alertadas
            for p in alert_persons:
                p.alert_sent = True

            return True

        except Exception as e:
            logger.error(f"Error enviando alerta de Telegram: {e}")
            return False

    def send_status(self, message: str) -> bool:
        """Envía un mensaje de estado (no una alerta)."""
        try:
            loop = self._get_loop()
            loop.run_until_complete(
                self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                )
            )
            return True
        except Exception as e:
            logger.error(f"Error enviando mensaje de estado: {e}")
            return False

    def send_startup_message(self):
        """Envía mensaje indicando que el sistema arrancó."""
        self.send_status(
            "✅ *Sistema de Alerta Puente Chaco-Corrientes*\n\n"
            "El sistema de monitoreo ha iniciado.\n"
            "Monitoreando stream en vivo...\n\n"
            "_Las alertas se enviarán a este grupo._"
        )

    def send_shutdown_message(self):
        """Envía mensaje indicando que el sistema se detuvo."""
        self.send_status(
            "🔴 *Sistema de Alerta - Detenido*\n\n"
            "El sistema de monitoreo se ha detenido.\n"
            "_Verificar el servicio._"
        )
