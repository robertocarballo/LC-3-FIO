"""Adapta el terminal físico al puerto de E/S consumido por la máquina.

Bootstrap construye ConsoleIO; este adaptador concentra stdin/stdout, msvcrt y
la espera de sondeo Windows. No posee estado de CPU ni captura streams, de modo
que una redirección posterior de sys.stdout sigue afectando a cada operación.
"""

import sys
import time
from typing import Optional

try:
    import msvcrt

    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


class ConsoleIO:
    """Implementa E/S del anfitrión sin capturar los streams del proceso."""

    def write_text(self, text: str) -> None:
        """Escribe la salida de programa en el stdout actual y fuerza su vaciado."""
        sys.stdout.write(text)
        sys.stdout.flush()

    def read_char(self) -> int:
        """Lee para TRAP nativo; Windows normaliza CR y POSIX devuelve cero en EOF.

        Puede bloquear hasta recibir un carácter. Los errores del terminal se
        propagan a la máquina sin sustituirse por datos de entrada.
        """
        if HAS_MSVCRT:
            ch = msvcrt.getch()
            if ch == b"\r":
                return 10
            return ord(ch)
        ch = sys.stdin.read(1)
        return ord(ch) if ch else 0

    def poll_key(self) -> Optional[bool]:
        """Sondea Windows sin consumir; espera 1 ms sólo si no hay tecla.

        POSIX devuelve None sin dormir ni leer stdin: no ofrece sondeo físico.
        """
        if not HAS_MSVCRT:
            return None
        if msvcrt.kbhit():
            return True
        time.sleep(0.001)
        return False

    def read_key(self) -> Optional[int]:
        """Lee para KBDR en Windows; en POSIX devuelve None sin bloquear.

        La lectura Windows usa getch y normaliza CR a LF como read_char.
        """
        if HAS_MSVCRT:
            return self.read_char()
        return None

    def report(self, text: str) -> None:
        """Imprime un diagnóstico en stdout con el salto de línea de print."""
        print(text)
