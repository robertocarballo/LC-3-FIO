"""Compone la máquina real y fija rutas de recursos para CLI, GUI y pruebas.

La factoría conecta el dominio con ConsoleIO y la imagen real del SO. Las
rutas parten de este archivo, no del directorio de trabajo del invocador.
"""

from pathlib import Path

from lc3.domain.machine import LC3Simulator
from lc3.domain.os_image import get_os_image
from lc3.infrastructure.terminal import ConsoleIO

# Ubicaciones compartidas por presentación y pruebas; examples permanece en raíz.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"


def create_simulator() -> LC3Simulator:
    """Entrega a CLI, GUI o pruebas una máquina con terminal e imagen SO reales."""
    return LC3Simulator(ConsoleIO(), get_os_image())
