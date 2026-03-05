"""
Módulo de detección de personas usando YOLOv8.

Detecta personas en un frame y retorna sus bounding boxes
con coordenadas normalizadas y confianza.
"""

import logging
import numpy as np
from typing import List, Dict
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# Clase "person" en COCO dataset = ID 0
PERSON_CLASS_ID = 0


class Detection:
    """Representa una persona detectada en un frame."""

    def __init__(self, x1: int, y1: int, x2: int, y2: int, confidence: float):
        self.x1 = x1  # Esquina superior izquierda X
        self.y1 = y1  # Esquina superior izquierda Y
        self.x2 = x2  # Esquina inferior derecha X
        self.y2 = y2  # Esquina inferior derecha Y
        self.confidence = confidence

    @property
    def center_x(self) -> int:
        return (self.x1 + self.x2) // 2

    @property
    def center_y(self) -> int:
        return (self.y1 + self.y2) // 2

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    def __repr__(self):
        return (
            f"Detection(center=({self.center_x},{self.center_y}), "
            f"conf={self.confidence:.2f})"
        )


class PersonDetector:
    """Detector de personas usando YOLOv8."""

    def __init__(self, model_name: str = "yolov8n.pt", confidence: float = 0.4):
        self.confidence = confidence
        logger.info(f"Cargando modelo YOLO: {model_name}")
        self.model = YOLO(model_name)
        logger.info("Modelo YOLO cargado exitosamente")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Detecta personas en un frame.

        Args:
            frame: Imagen como numpy array (BGR, formato OpenCV)

        Returns:
            Lista de Detection con las personas encontradas
        """
        results = self.model(
            frame,
            conf=self.confidence,
            classes=[PERSON_CLASS_ID],  # Solo detectar personas
            verbose=False,
        )

        detections = []
        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                conf = float(box.conf[0])

                detections.append(Detection(
                    x1=int(x1), y1=int(y1),
                    x2=int(x2), y2=int(y2),
                    confidence=conf
                ))

        if detections:
            logger.debug(f"Detectadas {len(detections)} personas")

        return detections
