"""Contrato de E/S física que la máquina consume sin conocer el terminal.

La composición proporciona un HostIO y las presentaciones pueden sustituir
operaciones concretas mediante los callbacks de LC3Simulator. Las capacidades
no bloqueantes ausentes se expresan con None, no mediante lecturas bloqueantes.
"""

from typing import Optional, Protocol


class HostIO(Protocol):
    """Describe salida, lectura y diagnósticos del anfitrión para la máquina."""

    def write_text(self, text: str) -> None:
        """Emite texto de TRAP o DDR y hace visible la salida pendiente."""
        ...

    def read_char(self) -> int:
        """Lee un carácter para TRAP nativo; puede bloquear y devuelve cero en EOF."""
        ...

    def poll_key(self) -> Optional[bool]:
        """Consulta sin consumir; None indica que no hay capacidad de sondeo."""
        ...

    def read_key(self) -> Optional[int]:
        """Consume una tecla para KBDR, o devuelve None si no está disponible la capacidad."""
        ...

    def report(self, text: str) -> None:
        """Emite un diagnóstico separado de los callbacks de salida del programa."""
        ...
