"""Adapta archivos de programas para CLI, GUI y pruebas.

Delega algoritmos al ensamblador y carga directa a la máquina. Los escritores
no son transaccionales: E/S puede dejar archivos previos o parciales y sus
excepciones se propagan. No controla ejecución ni presenta errores.
"""

import os
from typing import Dict, List, Tuple
from lc3.domain.isa import MASK_16
from lc3.domain.assembler import LC3Assembler
from lc3.domain.machine import LC3Simulator


def write_obj_file(filename: str, orig_addr: int, words: List[int]) -> None:
    """Sobrescribe OBJ big-endian con origen y palabras recortadas a 16 bits.

    Lo llama ``assemble_file`` o el consumidor directo; no usa estado de
    instancia. Propaga errores de E/S o conversión del origen y puede dejar
    un archivo truncado/parcial; no valida ni escribe símbolos.
    """
    with open(filename, "wb") as f:
        # Dirección de origen (2 bytes big-endian)
        f.write(orig_addr.to_bytes(2, byteorder="big"))
        # Palabras de código/datos
        for w in words:
            f.write((w & MASK_16).to_bytes(2, byteorder="big"))


def write_sym_file(filename: str, symbols: Dict[str, int]) -> None:
    """Sobrescribe SYM UTF-8 ordenando establemente por dirección.

    ``assemble_file`` o un consumidor directo presta la tabla, que no se
    modifica. Propaga errores de E/S y puede dejar salida parcial.
    """
    with open(filename, "w", encoding="utf-8") as f:
        f.write("// Symbol table\n")
        f.write("// Scope level 0:\n")
        f.write("//\tSymbol Name       Page Address\n")
        f.write("//\t----------------  ------------\n")
        for sym, addr in sorted(symbols.items(), key=lambda x: x[1]):
            f.write(f"//\t{sym:<16}  x{addr:04X}\n")


def write_hex_file(filename: str, orig_addr: int, words: List[int]) -> None:
    """Sobrescribe HEX UTF-8 con direcciones consecutivas y valores sin máscara.

    ``assemble_file`` o un consumidor directo proporciona todos los datos;
    no usa estado de instancia. Propaga errores de E/S y deja lo ya escrito
    si falla; las direcciones no se recortan al espacio de 16 bits.
    """
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# LC-3 HEX DUMP: ORIG x{orig_addr:04X}\n")
        for i, w in enumerate(words):
            f.write(f"x{orig_addr + i:04X}: {w:04X}\n")


def assemble_file(
    src_path: str, obj_path: str = None, sym_path: str = None, hex_path: str = None
) -> Tuple[int, int]:
    """Lee una fuente y escribe OBJ, SYM y opcionalmente HEX, en ese orden.

    CLI y GUI delegan aquí su pipeline de archivos. Lee UTF-8 sustituyendo bytes
    inválidos y crea un ensamblador propio. Deriva OBJ desde el nombre fuente
    si falta y SYM desde OBJ; sólo genera HEX si su ruta es verdadera.
    Sobrescribe las salidas secuencialmente, sin rollback: un fallo posterior
    conserva los archivos anteriores y puede dejar el actual incompleto.

    Returns:
        Tuple[int, int]: Origen y cantidad de palabras ensambladas.

    Raises:
        AssemblyError: La fuente es rechazada antes de escribir salidas.
        OSError: Falla la lectura o alguno de los escritores.
    """
    if obj_path is None:
        if src_path.lower().endswith(".asm"):
            obj_path = src_path[:-4] + ".obj"
        else:
            obj_path = src_path + ".obj"

    if sym_path is None:
        sym_path = obj_path.rsplit(".", 1)[0] + ".sym"

    with open(src_path, "r", encoding="utf-8", errors="replace") as f:
        source_text = f.read()

    assembler = LC3Assembler()
    orig, words, symbols = assembler.assemble(source_text)
    write_obj_file(obj_path, orig, words)
    write_sym_file(sym_path, symbols)

    if hex_path:
        write_hex_file(hex_path, orig, words)

    return orig, len(words)


def load_obj(sim: LC3Simulator, filename: str) -> int:
    """Lee OBJ completo antes de cargar palabras directas y fijar PC en sim.

    CLI, GUI y pruebas invocan este adaptador; delega a load_words sin reset
    ni efectos MMIO. Una cabecera sola es válida; ignora el byte final impar.

    Returns:
        int: Origen big-endian de la cabecera.
    Raises:
        ValueError: Menos de dos bytes; no se modifica la máquina.
        OSError: La apertura o lectura falla, antes de modificar la máquina.
    """
    with open(filename, "rb") as f:
        data = f.read()
    if len(data) < 2:
        raise ValueError(f"El archivo {filename} está vacío o es inválido.")
    orig = int.from_bytes(data[0:2], byteorder="big")
    return sim.load_words(
        orig,
        (
            int.from_bytes(data[i : i + 2], byteorder="big")
            for i in range(2, len(data) - 1, 2)
        ),
    )


def load_sym(sim: LC3Simulator, filename: str) -> None:
    """Fusiona SYM en symbols para los cargadores; ausente no cambia estado.

    Lee UTF-8 con reemplazo e ignora líneas sin dirección hexadecimal válida.
    Propaga errores de E/S; no borra etiquetas previas ni valida rango.
    """
    if not os.path.exists(filename):
        return
    with open(filename, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("//"):
                line = line.lstrip("/").strip()
            if (
                not line
                or line.startswith("---")
                or "Symbol Name" in line
                or "Scope" in line
            ):
                continue
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                addr_str = parts[1].replace("x", "").replace("X", "")
                try:
                    addr = int(addr_str, 16)
                    sim.symbols[addr] = name
                except ValueError:
                    pass
