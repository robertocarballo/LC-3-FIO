"""Paquete modular del núcleo y herramientas para la arquitectura LC-3.

Responsabilidad:
    Centralizar y exportar la API pública del proyecto: constantes de la ISA, ensamblador,
    máquina virtual, depurador interactivo e interfaz gráfica de usuario.
"""

from .core import (
    MEMORY_SIZE,
    MASK_16,
    NUM_REGISTERS,
    FL_POS,
    FL_ZRO,
    FL_NEG,
    sign_extend,
    to_uint16,
    to_int16,
    get_cc_name,
    disassemble_instruction,
)
from .assembler import (
    LC3Assembler,
    AssemblyError,
    assemble_file,
)
from .sim import LC3Simulator
from .debugger import LC3Debugger
from .gui import LC3GUI

__all__ = [
    "MEMORY_SIZE",
    "MASK_16",
    "NUM_REGISTERS",
    "FL_POS",
    "FL_ZRO",
    "FL_NEG",
    "sign_extend",
    "to_uint16",
    "to_int16",
    "get_cc_name",
    "disassemble_instruction",
    "LC3Assembler",
    "AssemblyError",
    "assemble_file",
    "LC3Simulator",
    "LC3Debugger",
    "LC3GUI",
]
