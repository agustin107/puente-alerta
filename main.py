"""
Puente Alerta - Sistema de Alerta Temprana
Puente Chaco-Corrientes

Pipeline principal que orquesta:
1. Captura de frames del stream de YouTube
2. Detección de personas con YOLOv8
3. Monitoreo de zonas de riesgo
4. Envío de alertas por Telegram

Uso:
    python main.py                  # Modo normal
    python main.py --calibrate      # Modo calibración (guarda screenshots)
    python main.py --test-telegram  # Envía mensaje de prueba a Telegram
"""

import sys
import time
import signal
import logging
import argparse
from datetime import datetime

from config.settings import settings
from modules.stream_capture import StreamCapture
from modules.person_detector import PersonDetector
from modules.zone_monitor import ZoneMonitor
from modules.telegram_alert import TelegramAlert

# ============================================
# Logging
# ============================================
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("puente-alerta")


class PuenteAlerta:
    """Pipeline principal del sistema de alerta."""

    def __init__(self):
        self.running = False

        # Inicializar módulos
        logger.info("=" * 50)
        logger.info("PUENTE ALERTA - Iniciando sistema")
        logger.info("=" * 50)

        self.stream = StreamCapture(settings.YOUTUBE_URL)
        self.detector = PersonDetector(
            model_name=settings.YOLO_MODEL,
            confidence=settings.DETECTION_CONFIDENCE,
        )
        self.monitor = ZoneMonitor(
            alert_threshold_seconds=settings.ALERT_THRESHOLD_SECONDS,
        )
        self.telegram = TelegramAlert(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=settings.TELEGRAM_CHAT_ID,
            cooldown_seconds=settings.ALERT_COOLDOWN_SECONDS,
        )

        # Manejar señales de terminación
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        """Maneja shutdown graceful."""
        logger.info("Señal de terminación recibida, cerrando...")
        self.running = False

    def run(self):
        """Ejecuta el pipeline principal en loop infinito."""
        self.running = True

        # Conectar al stream
        logger.info("Conectando al stream de YouTube...")
        retry_count = 0
        max_retries = 10

        while not self.stream.connect() and retry_count < max_retries:
            retry_count += 1
            wait_time = min(30, 5 * retry_count)
            logger.warning(
                f"No se pudo conectar al stream. "
                f"Reintento {retry_count}/{max_retries} en {wait_time}s..."
            )
            time.sleep(wait_time)

        if retry_count >= max_retries:
            logger.error("No se pudo conectar al stream después de todos los reintentos")
            return

        # Notificar inicio
        self.telegram.send_startup_message()
        logger.info("Sistema iniciado. Monitoreando...")

        # Contadores para logging periódico
        frames_processed = 0
        last_status_log = time.time()
        status_log_interval = 300  # Log de estado cada 5 minutos

        try:
            while self.running:
                loop_start = time.time()

                # 1. Capturar frame
                frame = self.stream.capture_frame()
                if frame is None:
                    logger.warning("Frame nulo, esperando...")
                    time.sleep(5)
                    continue

                frame_height, frame_width = frame.shape[:2]

                # 2. Detectar personas
                detections = self.detector.detect(frame)

                # 3. Actualizar monitor de zonas
                alerts = self.monitor.update(
                    detections, frame_width, frame_height
                )

                # 4. Enviar alertas si corresponde
                if alerts:
                    self.telegram.send_alert(frame, detections, alerts)

                frames_processed += 1

                # Log periódico de estado
                if time.time() - last_status_log >= status_log_interval:
                    status = self.monitor.get_status()
                    logger.info(
                        f"Estado: {frames_processed} frames procesados | "
                        f"Personas rastreadas: {status['tracked_persons']} | "
                        f"En zonas de riesgo: {status['persons_in_risk_zones']}"
                    )
                    last_status_log = time.time()

                # Esperar el intervalo configurado
                elapsed = time.time() - loop_start
                sleep_time = max(0, settings.FRAME_INTERVAL - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Error en el pipeline: {e}", exc_info=True)

        finally:
            logger.info("Cerrando sistema...")
            self.telegram.send_shutdown_message()
            self.stream.disconnect()
            logger.info("Sistema cerrado correctamente")


def calibrate_mode():
    """
    Modo calibración: captura screenshots del stream para
    ayudar a definir las zonas de riesgo.
    """
    import cv2
    import os

    logger.info("=== MODO CALIBRACIÓN ===")
    logger.info("Capturando screenshots del stream para calibración...")

    stream = StreamCapture(settings.YOUTUBE_URL)
    if not stream.connect():
        logger.error("No se pudo conectar al stream")
        return

    output_dir = "calibration_screenshots"
    os.makedirs(output_dir, exist_ok=True)

    for i in range(5):
        frame = stream.capture_frame()
        if frame is not None:
            h, w = frame.shape[:2]

            # Dibujar grilla de referencia (cada 10%)
            for pct in range(10, 100, 10):
                x = int(w * pct / 100)
                y = int(h * pct / 100)
                cv2.line(frame, (x, 0), (x, h), (100, 100, 100), 1)
                cv2.line(frame, (0, y), (w, y), (100, 100, 100), 1)
                cv2.putText(
                    frame, f"{pct}%",
                    (x + 2, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1
                )
                cv2.putText(
                    frame, f"{pct}%",
                    (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1
                )

            filename = f"{output_dir}/calibration_{i+1}.jpg"
            cv2.imwrite(filename, frame)
            logger.info(f"Screenshot guardado: {filename}")

        time.sleep(3)

    stream.disconnect()
    logger.info(f"\nScreenshots guardados en '{output_dir}/'")
    logger.info("Usa estas imágenes para definir las zonas de riesgo.")
    logger.info("Las coordenadas están en porcentajes (grilla dibujada).")


def test_telegram():
    """Envía un mensaje de prueba a Telegram."""
    logger.info("Enviando mensaje de prueba a Telegram...")
    alert = TelegramAlert(
        bot_token=settings.TELEGRAM_BOT_TOKEN,
        chat_id=settings.TELEGRAM_CHAT_ID,
    )
    success = alert.send_status(
        "🧪 *Mensaje de prueba*\n\n"
        "Si ves este mensaje, la conexión con Telegram "
        "está configurada correctamente.\n\n"
        f"_Enviado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
    )
    if success:
        logger.info("✅ Mensaje de prueba enviado correctamente")
    else:
        logger.error("❌ Error enviando mensaje de prueba")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Puente Alerta - Sistema de Alerta Temprana")
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Modo calibración: captura screenshots para definir zonas",
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Envía un mensaje de prueba a Telegram",
    )

    args = parser.parse_args()

    if args.calibrate:
        calibrate_mode()
    elif args.test_telegram:
        test_telegram()
    else:
        app = PuenteAlerta()
        app.run()
