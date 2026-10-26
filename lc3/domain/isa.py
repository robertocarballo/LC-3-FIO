"""Define la ISA y las conversiones puras compartidas por las capas LC-3.

Ensamblador, SO, simulador, depurador, GUI y pruebas consumen estas constantes
y funciones; el módulo no carga programas ni modifica el estado de la máquina.
El desensamblado delega en las conversiones locales y sólo devuelve texto.
"""

# Tamaño de memoria de la LC-3: 2^16 palabras de 16 bits (65,536 palabras)
MEMORY_SIZE = 65536

# Máscaras de 16 bits
MASK_16 = 0xFFFF
SIGN_BIT_16 = 0x8000

# Registros generales: R0 a R7 (8 registros de 16 bits)
NUM_REGISTERS = 8

# Condition Codes (Códigos de condición en el PSR)
FL_POS = 1 << 0  # 001 (P: Positivo > 0)
FL_ZRO = 1 << 1  # 010 (Z: Cero == 0)
FL_NEG = 1 << 2  # 100 (N: Negativo < 0)

# Opcodes (4 bits: bits [15:12])
OP_BR = 0x0  # 0000: Branch condicional
OP_ADD = 0x1  # 0001: Suma
OP_LD = 0x2  # 0010: Carga relativa a PC
OP_ST = 0x3  # 0011: Almacenamiento relativo a PC
OP_JSR = 0x4  # 0100: Salto a subrutina (JSR / JSRR)
OP_AND = 0x5  # 0101: AND lógico bit a bit
OP_LDR = 0x6  # 0110: Carga base + desplazamiento
OP_STR = 0x7  # 0111: Almacenamiento base + desplazamiento
OP_RTI = 0x8  # 1000: Retorno de interrupción
OP_NOT = 0x9  # 1001: NOT lógico (complemento a 1)
OP_LDI = 0xA  # 1010: Carga indirecta
OP_STI = 0xB  # 1011: Almacenamiento indirecto
OP_JMP = 0xC  # 1100: Salto incondicional / RET (JMP R7)
OP_RES = 0xD  # 1101: Reservado (no usado)
OP_LEA = 0xE  # 1110: Carga de dirección efectiva
OP_TRAP = 0xF  # 1111: Llamada al sistema (TRAP)

# Vectores de TRAP estándar
TRAP_GETC = 0x20  # Lee un carácter del teclado (sin eco)
TRAP_OUT = 0x21  # Imprime un carácter a consola
TRAP_PUTS = 0x22  # Imprime cadena de caracteres (null-terminated)
TRAP_IN = 0x23  # Pide un carácter por teclado (con mensaje y eco)
TRAP_PUTSP = 0x24  # Imprime cadena empaquetada (2 chars por palabra)
TRAP_HALT = 0x25  # Detiene la máquina

# Registros mapeados en memoria (Memory-Mapped I/O - MMIO)
MR_KBSR = 0xFE00  # Keyboard Status Register
MR_KBDR = 0xFE02  # Keyboard Data Register
MR_DSR = 0xFE04  # Display Status Register
MR_DDR = 0xFE06  # Display Data Register
MR_MCR = 0xFFFE  # Machine Control Register (bit 15: reloj)

# Nombres legibles de TRAP
TRAP_NAMES = {
    TRAP_GETC: "GETC",
    TRAP_OUT: "OUT",
    TRAP_PUTS: "PUTS",
    TRAP_IN: "IN",
    TRAP_PUTSP: "PUTSP",
    TRAP_HALT: "HALT",
}


def sign_extend(x: int, bit_count: int) -> int:
    """Extiende el signo para los consumidores de operandos de la ISA.

    Args:
        x: Campo entero; no se recortan previamente sus bits superiores.
        bit_count: Anchura positiva del campo, proporcionada por el llamador.

    Returns:
        int: Valor con los bits superiores activados si el bit de signo era uno.
    """
    if (x >> (bit_count - 1)) & 1:
        x |= -1 << bit_count
    return x


def to_uint16(val: int) -> int:
    """Convierte cualquier entero a un valor de 16 bits sin signo (0 a 0xFFFF)."""
    return val & MASK_16


def to_int16(val: int) -> int:
    """Convierte un valor de 16 bits sin signo a entero con signo (-32768 a 32767)."""
    val = val & MASK_16
    if val & SIGN_BIT_16:
        return val - 0x10000
    return val


def get_cc_name(cc: int) -> str:
    """Devuelve N, Z y P activos, en ese orden, o ``None`` como texto."""
    parts = []
    if cc & FL_NEG:
        parts.append("N")
    if cc & FL_ZRO:
        parts.append("Z")
    if cc & FL_POS:
        parts.append("P")
    return "".join(parts) if parts else "None"


def disassemble_instruction(instr: int, pc: int = 0, symbols: dict = None) -> str:
    """Devuelve texto de una palabra para vistas y comandos de depuración.

    Delega el enmascarado y la extensión de signo en helpers de este módulo.
    No consulta memoria ni modifica el mapa prestado por el invocador.

    Args:
        instr: Palabra que se recorta a 16 bits, sin validar su codificación.
        pc: Dirección de la instrucción, no el PC ya incrementado.
        symbols: Mapa opcional de dirección a nombre para destinos relativos.

    Returns:
        str: Mnemónico y operandos; el opcode reservado se muestra como .FILL.
    """
    instr = to_uint16(instr)
    op = (instr >> 12) & 0xF

    def fmt_addr(target_addr: int) -> str:
        """Formatea un destino de este desensamblado usando el mapa capturado."""
        target_addr &= MASK_16
        if symbols and target_addr in symbols:
            return f"{symbols[target_addr]} (x{target_addr:04X})"
        return f"x{target_addr:04X}"

    if op == OP_ADD or op == OP_AND:
        name = "ADD" if op == OP_ADD else "AND"
        dr = (instr >> 9) & 0x7
        sr1 = (instr >> 6) & 0x7
        if (instr >> 5) & 1:
            imm5 = sign_extend(instr & 0x1F, 5)
            return f"{name:<5} R{dr}, R{sr1}, #{imm5}"
        else:
            sr2 = instr & 0x7
            return f"{name:<5} R{dr}, R{sr1}, R{sr2}"

    elif op == OP_NOT:
        dr = (instr >> 9) & 0x7
        sr = (instr >> 6) & 0x7
        return f"NOT   R{dr}, R{sr}"

    elif op == OP_BR:
        n = (instr >> 11) & 1
        z = (instr >> 10) & 1
        p = (instr >> 9) & 1
        cond = ""
        if n:
            cond += "n"
        if z:
            cond += "z"
        if p:
            cond += "p"
        if not cond:
            cond = "nop"
        offset9 = sign_extend(instr & 0x1FF, 9)
        target = (pc + 1 + offset9) & MASK_16
        return f"BR{cond:<4} {fmt_addr(target)}"

    elif op in (OP_LD, OP_LDI, OP_LEA, OP_ST, OP_STI):
        names = {OP_LD: "LD", OP_LDI: "LDI", OP_LEA: "LEA", OP_ST: "ST", OP_STI: "STI"}
        r = (instr >> 9) & 0x7
        offset9 = sign_extend(instr & 0x1FF, 9)
        target = (pc + 1 + offset9) & MASK_16
        return f"{names[op]:<5} R{r}, {fmt_addr(target)}"

    elif op in (OP_LDR, OP_STR):
        name = "LDR" if op == OP_LDR else "STR"
        r = (instr >> 9) & 0x7
        base_r = (instr >> 6) & 0x7
        offset6 = sign_extend(instr & 0x3F, 6)
        return f"{name:<5} R{r}, R{base_r}, #{offset6}"

    elif op == OP_JMP:
        base_r = (instr >> 6) & 0x7
        if base_r == 7:
            return "RET"
        return f"JMP   R{base_r}"

    elif op == OP_JSR:
        if (instr >> 11) & 1:
            offset11 = sign_extend(instr & 0x7FF, 11)
            target = (pc + 1 + offset11) & MASK_16
            return f"JSR   {fmt_addr(target)}"
        else:
            base_r = (instr >> 6) & 0x7
            return f"JSRR  R{base_r}"

    elif op == OP_TRAP:
        trapvect = instr & 0xFF
        if trapvect in TRAP_NAMES:
            return TRAP_NAMES[trapvect]
        return f"TRAP  x{trapvect:02X}"

    elif op == OP_RTI:
        return "RTI"

    else:
        return f".FILL x{instr:04X}"
