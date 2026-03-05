"""
Módulo de monitoreo de zonas de riesgo.

Define zonas en la imagen donde una persona inmóvil
podría indicar riesgo. Rastrea personas entre frames
y determina cuánto tiempo llevan en una zona.

Las zonas se definen como porcentajes de la imagen (0.0 - 1.0)
para ser independientes de la resolución.
"""

import time
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from modules.person_detector import Detection

logger = logging.getLogger(__name__)


@dataclass
class RiskZone:
    """
    Zona de riesgo definida como rectángulo en porcentajes de la imagen.

    Ejemplo: RiskZone("baranda_norte", 0.0, 0.6, 1.0, 0.85)
    define una franja horizontal en el 60-85% vertical de la imagen.
    """
    name: str
    x1_pct: float  # 0.0 - 1.0
    y1_pct: float  # 0.0 - 1.0
    x2_pct: float  # 0.0 - 1.0
    y2_pct: float  # 0.0 - 1.0
    severity: str = "high"  # "high", "medium", "low"

    def contains_point(self, x_pct: float, y_pct: float) -> bool:
        """Verifica si un punto (en porcentajes) está dentro de la zona."""
        return (self.x1_pct <= x_pct <= self.x2_pct and
                self.y1_pct <= y_pct <= self.y2_pct)


@dataclass
class TrackedPerson:
    """Persona siendo rastreada entre frames."""
    id: int
    center_x: int
    center_y: int
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    in_risk_zone: Optional[str] = None
    risk_zone_since: Optional[float] = None
    alert_sent: bool = False

    @property
    def time_in_zone(self) -> float:
        """Tiempo en segundos que lleva en la zona de riesgo."""
        if self.risk_zone_since is None:
            return 0
        return time.time() - self.risk_zone_since

    @property
    def total_time_tracked(self) -> float:
        return self.last_seen - self.first_seen


class ZoneMonitor:
    """
    Monitorea zonas de riesgo y rastrea personas.

    Usa un algoritmo simple de proximidad para asociar
    detecciones entre frames (no necesita deep learning).
    """

    # Distancia máxima (en píxeles) para considerar que
    # dos detecciones son la misma persona entre frames
    MAX_MATCH_DISTANCE = 80

    # Tiempo sin ver una persona antes de eliminarla del tracking
    PERSON_TIMEOUT = 15  # segundos

    def __init__(self, alert_threshold_seconds: int = 180):
        self.alert_threshold = alert_threshold_seconds
        self.risk_zones: List[RiskZone] = []
        self.tracked_persons: Dict[int, TrackedPerson] = {}
        self._next_person_id = 0

        # Zonas por defecto - DEBEN ser calibradas con el stream real
        # Estas son zonas genéricas para un puente visto de costado
        self._setup_default_zones()

    def _setup_default_zones(self):
        """
        Configura zonas de riesgo por defecto.

        IMPORTANTE: Estas zonas son genéricas y DEBEN ser ajustadas
        mirando el stream real. Cada cámara tiene un ángulo diferente.

        Para calibrar:
        1. Capturar un screenshot del stream
        2. Identificar visualmente las barandas/bordes
        3. Convertir las coordenadas a porcentajes de la imagen
        4. Actualizar las zonas aquí o en zones_config.json

        Las coordenadas son porcentajes (0.0 = izquierda/arriba, 1.0 = derecha/abajo)
        """
        self.risk_zones = [
            # Zona: borde superior de la imagen (posible baranda superior)
            RiskZone(
                name="baranda_superior",
                x1_pct=0.05, y1_pct=0.0,
                x2_pct=0.95, y2_pct=0.25,
                severity="high"
            ),
            # Zona: borde inferior de la imagen (posible baranda inferior)
            RiskZone(
                name="baranda_inferior",
                x1_pct=0.05, y1_pct=0.75,
                x2_pct=0.95, y2_pct=1.0,
                severity="high"
            ),
            # Zona: extremo izquierdo (posible borde del puente)
            RiskZone(
                name="extremo_izquierdo",
                x1_pct=0.0, y1_pct=0.0,
                x2_pct=0.08, y2_pct=1.0,
                severity="medium"
            ),
            # Zona: extremo derecho
            RiskZone(
                name="extremo_derecho",
                x1_pct=0.92, y1_pct=0.0,
                x2_pct=1.0, y2_pct=1.0,
                severity="medium"
            ),
        ]
        logger.info(f"Configuradas {len(self.risk_zones)} zonas de riesgo por defecto")

    def load_zones_from_config(self, zones_config: List[Dict]):
        """
        Carga zonas desde configuración externa.

        Args:
            zones_config: Lista de dicts con keys:
                name, x1_pct, y1_pct, x2_pct, y2_pct, severity
        """
        self.risk_zones = []
        for z in zones_config:
            self.risk_zones.append(RiskZone(**z))
        logger.info(f"Cargadas {len(self.risk_zones)} zonas desde configuración")

    def _find_matching_person(
        self, detection: Detection
    ) -> Optional[int]:
        """
        Busca si una detección corresponde a una persona ya rastreada.
        Usa distancia euclidiana simple entre centros.
        """
        min_dist = float("inf")
        best_id = None

        for person_id, person in self.tracked_persons.items():
            dist = (
                (detection.center_x - person.center_x) ** 2 +
                (detection.center_y - person.center_y) ** 2
            ) ** 0.5

            if dist < min_dist and dist < self.MAX_MATCH_DISTANCE:
                min_dist = dist
                best_id = person_id

        return best_id

    def _check_risk_zones(
        self, detection: Detection, frame_width: int, frame_height: int
    ) -> Optional[str]:
        """Verifica si una detección está en alguna zona de riesgo."""
        # Convertir coordenadas de píxeles a porcentajes
        # Usamos el punto inferior central (los pies de la persona)
        x_pct = detection.center_x / frame_width
        y_pct = detection.y2 / frame_height  # Parte inferior del bounding box

        for zone in self.risk_zones:
            if zone.contains_point(x_pct, y_pct):
                return zone.name

        return None

    def update(
        self,
        detections: List[Detection],
        frame_width: int,
        frame_height: int,
    ) -> List[TrackedPerson]:
        """
        Actualiza el estado del monitor con nuevas detecciones.

        Returns:
            Lista de TrackedPerson que superan el umbral de alerta
        """
        now = time.time()
        matched_ids = set()
        alerts = []

        # 1. Asociar detecciones con personas existentes
        for det in detections:
            person_id = self._find_matching_person(det)

            if person_id is not None:
                # Actualizar persona existente
                person = self.tracked_persons[person_id]
                person.center_x = det.center_x
                person.center_y = det.center_y
                person.last_seen = now
                matched_ids.add(person_id)
            else:
                # Nueva persona
                person_id = self._next_person_id
                self._next_person_id += 1
                person = TrackedPerson(
                    id=person_id,
                    center_x=det.center_x,
                    center_y=det.center_y,
                )
                self.tracked_persons[person_id] = person
                matched_ids.add(person_id)

            # Verificar zona de riesgo
            zone_name = self._check_risk_zones(det, frame_width, frame_height)

            if zone_name:
                if person.in_risk_zone != zone_name:
                    # Entró a una nueva zona de riesgo
                    person.in_risk_zone = zone_name
                    person.risk_zone_since = now
                    person.alert_sent = False
                    logger.info(
                        f"Persona #{person.id} entró en zona '{zone_name}'"
                    )
                # Si ya estaba en la misma zona, el timer sigue corriendo
            else:
                if person.in_risk_zone is not None:
                    logger.debug(
                        f"Persona #{person.id} salió de zona "
                        f"'{person.in_risk_zone}'"
                    )
                person.in_risk_zone = None
                person.risk_zone_since = None
                person.alert_sent = False

            # Verificar si supera el umbral de alerta
            if (
                person.in_risk_zone is not None
                and person.time_in_zone >= self.alert_threshold
                and not person.alert_sent
            ):
                alerts.append(person)
                logger.warning(
                    f"⚠️ ALERTA: Persona #{person.id} en zona "
                    f"'{person.in_risk_zone}' por "
                    f"{person.time_in_zone:.0f}s"
                )

        # 2. Eliminar personas que no se ven hace rato
        expired = [
            pid for pid, p in self.tracked_persons.items()
            if now - p.last_seen > self.PERSON_TIMEOUT
        ]
        for pid in expired:
            logger.debug(f"Persona #{pid} expirada del tracking")
            del self.tracked_persons[pid]

        return alerts

    def get_status(self) -> Dict:
        """Retorna estado actual del monitor para logging/debug."""
        return {
            "tracked_persons": len(self.tracked_persons),
            "persons_in_risk_zones": sum(
                1 for p in self.tracked_persons.values()
                if p.in_risk_zone is not None
            ),
            "risk_zones": len(self.risk_zones),
        }
