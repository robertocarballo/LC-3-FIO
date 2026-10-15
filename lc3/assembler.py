"""
lc3_assembler.py - Ensamblador de dos pasadas para la arquitectura LC-3.
Soporta todas las instrucciones estándar, pseudoinstrucciones y directivas.
Genera binarios .obj estándar (big-endian) y tablas de símbolos .sym.
"""

import re
import sys
from typing import Dict, List, Tuple, Optional
from .core import (
    MASK_16,
    OP_BR, OP_ADD, OP_LD, OP_ST, OP_JSR, OP_AND, OP_LDR, OP_STR,
    OP_RTI, OP_NOT, OP_LDI, OP_STI, OP_JMP, OP_LEA, OP_TRAP,
    TRAP_GETC, TRAP_OUT, TRAP_PUTS, TRAP_IN, TRAP_PUTSP, TRAP_HALT,
    to_uint16
)

REGISTERS = {f"R{i}": i for i in range(8)}

PSEUDO_OPS = {
    "GETC":  (OP_TRAP << 12) | TRAP_GETC,
    "OUT":   (OP_TRAP << 12) | TRAP_OUT,
    "PUTS":  (OP_TRAP << 12) | TRAP_PUTS,
    "IN":    (OP_TRAP << 12) | TRAP_IN,
    "PUTSP": (OP_TRAP << 12) | TRAP_PUTSP,
    "HALT":  (OP_TRAP << 12) | TRAP_HALT,
    "RET":   (OP_JMP << 12)  | (7 << 6),  # JMP R7
}

RESERVED_WORDS = set(REGISTERS.keys()) | set(PSEUDO_OPS.keys()) | {
    "ADD", "AND", "NOT", "BR", "BRN", "BRZ", "BRP", "BRNZ", "BRNP", "BRZP", "BRNZP",
    "JMP", "JSR", "JSRR", "LD", "LDI", "LDR", "LEA", "ST", "STI", "STR", "TRAP", "RTI",
    ".ORIG", ".END", ".FILL", ".BLKW", ".STRINGZ"
}


class AssemblyError(Exception):
    def __init__(self, line_num: int, line_text: str, message: str):
        self.line_num = line_num
        self.line_text = line_text
        self.message = message
        super().__init__(f"Línea {line_num}: {message}\n  -> {line_text.strip()}")


def parse_number(token: str) -> Optional[int]:
    """Parsea representaciones numéricas: #123, #-5, x3000, 0x3000, b1010, etc."""
    token = token.strip()
    if not token:
        return None
    try:
        sign = 1
        if token.startswith('-'):
            sign = -1
            token = token[1:]
        elif token.startswith('+'):
            token = token[1:]

        upper = token.upper()
        if upper.startswith('#'):
            return sign * int(token[1:], 10)
        elif upper.startswith('X'):
            return sign * int(token[1:], 16)
        elif upper.startswith('0X'):
            return sign * int(token[2:], 16)
        elif upper.startswith('B'):
            return sign * int(token[1:], 2)
        elif upper.startswith('0B'):
            return sign * int(token[2:], 2)
        elif token.isdigit():
            return sign * int(token, 10)
    except ValueError:
        return None
    return None


def parse_register(token: str) -> Optional[int]:
    """Parsea un nombre de registro como R0-R7."""
    t = token.strip().upper()
    return REGISTERS.get(t)


def unescape_string(s: str) -> str:
    """Procesa secuencias de escape estándar dentro de .STRINGZ."""
    escapes = {
        r'\n': '\n',
        r'\t': '\t',
        r'\r': '\r',
        r'\0': '\0',
        r'\"': '"',
        r'\\': '\\',
    }
    for k, v in escapes.items():
        s = s.replace(k, v)
    return s


def tokenize_line(line: str) -> List[str]:
    """
    Divide una línea en tokens considerando strings entre comillas y comentarios (; o #).
    """
    # Eliminar comentarios que no estén dentro de comillas
    cleaned = []
    in_quotes = False
    escape = False
    for char in line:
        if char == '"' and not escape:
            in_quotes = not in_quotes
        elif char == ';' and not in_quotes:
            break
        cleaned.append(char)
        if char == '\\' and not escape:
            escape = True
        else:
            escape = False
    line_str = "".join(cleaned).strip()
    if not line_str:
        return []

    # Extraer tokens preservando cadenas entre comillas
    pattern = r'".*?"|[^\s,]+'
    tokens = re.findall(pattern, line_str)
    return tokens


class LC3Assembler:
    def __init__(self):
        self.symbols: Dict[str, int] = {}
        self.orig_addr: Optional[int] = None
        self.instructions: List[Tuple[int, int, str]] = []  # (address, value, debug_text)

    def assemble(self, source_text: str) -> Tuple[int, List[int], Dict[str, int]]:
        """
        Ensambla código fuente LC-3.
        Retorna (orig_address, list_of_16bit_words, symbol_table).
        """
        lines = source_text.splitlines()
        self.symbols.clear()
        self.orig_addr = None
        self.instructions.clear()

        # ==================== PASADA 1 ====================
        # Encontrar .ORIG, recolectar etiquetas y calcular direcciones de memoria
        parsed_lines = []
        current_pc = None
        saw_end = False

        for idx, raw_line in enumerate(lines, start=1):
            tokens = tokenize_line(raw_line)
            if not tokens:
                continue

            if saw_end:
                break

            # Identificar si hay una etiqueta al inicio
            first_token = tokens[0]
            upper_first = first_token.upper()

            label = None
            # Una etiqueta puede terminar con ':' o ser una palabra que no es directiva ni mnemónico
            has_colon = first_token.endswith(':')
            potential_label = first_token[:-1] if has_colon else first_token

            is_reserved = (upper_first in RESERVED_WORDS or 
                           upper_first.startswith("BR") or 
                           upper_first.startswith("."))

            if has_colon or (not is_reserved and parse_register(first_token) is None and parse_number(first_token) is None):
                label = potential_label
                tokens = tokens[1:]

            if label:
                clean_label = label.strip()
                if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', clean_label):
                    raise AssemblyError(idx, raw_line, f"Nombre de etiqueta inválido '{clean_label}'. Debe comenzar con letra o guión bajo.")
                if clean_label.upper() in RESERVED_WORDS or clean_label.upper().startswith("BR"):
                    raise AssemblyError(idx, raw_line, f"La etiqueta '{clean_label}' es una palabra reservada o mnemónico de la ISA.")
                if clean_label in self.symbols:
                    raise AssemblyError(idx, raw_line, f"Etiqueta duplicada '{clean_label}'.")

            if not tokens:
                # Línea que solo tenía etiqueta
                if label:
                    if self.orig_addr is None:
                        raise AssemblyError(idx, raw_line, "La etiqueta aparece antes de la directiva .ORIG.")
                    self.symbols[label] = current_pc
                    parsed_lines.append((idx, raw_line, label, None, []))
                continue

            mnemonic = tokens[0].upper()
            args = tokens[1:]

            if mnemonic == ".ORIG":
                if self.orig_addr is not None:
                    raise AssemblyError(idx, raw_line, "Múltiples directivas .ORIG encontradas.")
                if not args:
                    raise AssemblyError(idx, raw_line, "La directiva .ORIG requiere una dirección (ej: .ORIG x3000).")
                addr = parse_number(args[0])
                if addr is None or addr < 0 or addr > 0xFFFF:
                    raise AssemblyError(idx, raw_line, f"Dirección .ORIG inválida '{args[0]}'.")
                self.orig_addr = addr
                current_pc = addr
                if label:
                    self.symbols[label] = current_pc
                parsed_lines.append((idx, raw_line, label, mnemonic, args))
                continue

            if self.orig_addr is None:
                raise AssemblyError(idx, raw_line, "El programa debe iniciar con la directiva .ORIG.")

            if mnemonic == ".END":
                saw_end = True
                parsed_lines.append((idx, raw_line, label, mnemonic, args))
                break

            # Si había etiqueta en esta línea, se asigna al PC actual
            if label:
                self.symbols[label] = current_pc

            # Calcular el espacio que ocupa esta instrucción o directiva
            line_size = 1
            if mnemonic == ".BLKW":
                if not args:
                    raise AssemblyError(idx, raw_line, ".BLKW requiere una cantidad de palabras (ej: .BLKW #10).")
                count = parse_number(args[0])
                if count is None or count <= 0:
                    raise AssemblyError(idx, raw_line, f"Cantidad inválida para .BLKW '{args[0]}'.")
                line_size = count
            elif mnemonic == ".STRINGZ":
                if not args:
                    raise AssemblyError(idx, raw_line, ".STRINGZ requiere una cadena entre comillas.")
                joined = " ".join(args)
                if not (joined.startswith('"') and joined.endswith('"')):
                    raise AssemblyError(idx, raw_line, ".STRINGZ requiere una cadena encerrada en comillas dobles.")
                content = unescape_string(joined[1:-1])
                line_size = len(content) + 1  # Incluye el carácter nulo terminador '\0'

            parsed_lines.append((idx, raw_line, label, mnemonic, args, current_pc, line_size))
            current_pc += line_size
            if current_pc > 0x10000:
                raise AssemblyError(idx, raw_line, "El programa excede el tamaño de memoria de 16 bits de la LC-3.")

        if self.orig_addr is None:
            raise AssemblyError(1, "", "No se encontró la directiva .ORIG en el archivo.")
        if not saw_end:
            raise AssemblyError(len(lines), "", "Falta la directiva .END al final del archivo.")

        # ==================== PASADA 2 ====================
        # Codificación de instrucciones y resolución de símbolos
        words: List[int] = []

        for item in parsed_lines:
            if len(item) == 5:
                # Directivas .ORIG o .END o líneas de solo etiqueta
                idx, raw_line, label, mnemonic, args = item
                if mnemonic == ".ORIG" and label:
                    # Ya guardado en símbolos
                    pass
                continue

            idx, raw_line, label, mnemonic, args, pc, size = item

            # Directivas
            if mnemonic == ".FILL":
                if not args:
                    raise AssemblyError(idx, raw_line, ".FILL requiere un valor numérico o etiqueta.")
                val = parse_number(args[0])
                if val is None:
                    # Debe ser una etiqueta
                    if args[0] not in self.symbols:
                        raise AssemblyError(idx, raw_line, f"Símbolo no definido '{args[0]}' en .FILL.")
                    val = self.symbols[args[0]]
                words.append(to_uint16(val))
                self.instructions.append((pc, to_uint16(val), raw_line))
                continue

            elif mnemonic == ".BLKW":
                count = parse_number(args[0])
                for i in range(count):
                    words.append(0)
                    self.instructions.append((pc + i, 0, f".BLKW [{i}]"))
                continue

            elif mnemonic == ".STRINGZ":
                joined = " ".join(args)
                content = unescape_string(joined[1:-1])
                for i, ch in enumerate(content):
                    words.append(ord(ch) & 0xFF)
                    self.instructions.append((pc + i, ord(ch) & 0xFF, f".STRINGZ '{ch}'"))
                words.append(0)  # Nulo terminador
                self.instructions.append((pc + len(content), 0, ".STRINGZ '\\0'"))
                continue

            # Pseudo-instrucciones TRAP y RET
            if mnemonic in PSEUDO_OPS:
                code = PSEUDO_OPS[mnemonic]
                words.append(code)
                self.instructions.append((pc, code, raw_line))
                continue

            # Instrucciones de la ISA
            code = self._encode_instruction(idx, raw_line, mnemonic, args, pc)
            words.append(code)
            self.instructions.append((pc, code, raw_line))

        return self.orig_addr, words, self.symbols

    def _resolve_offset(self, idx: int, raw_line: str, token: str, pc: int, bit_count: int) -> int:
        """
        Calcula y valida un desplazamiento relativo a PC (PCoffset).
        offset = target - (pc + 1)
        """
        target = parse_number(token)
        if target is None:
            if token not in self.symbols:
                raise AssemblyError(idx, raw_line, f"Etiqueta o símbolo no definido: '{token}'.")
            target = self.symbols[token]
            offset = target - (pc + 1)
        else:
            # Si se dio directamente un número, puede ser un desplazamiento literal
            offset = target

        min_val = -(1 << (bit_count - 1))
        max_val = (1 << (bit_count - 1)) - 1
        if offset < min_val or offset > max_val:
            raise AssemblyError(
                idx, raw_line,
                f"Desplazamiento PCoffset{bit_count} fuera de rango: {offset}. "
                f"Rango permitido: [{min_val}, {max_val}] (destino x{target:04X}, PC x{pc:04X})."
            )
        mask = (1 << bit_count) - 1
        return offset & mask

    def _encode_instruction(self, idx: int, raw_line: str, mnemonic: str, args: List[str], pc: int) -> int:
        # 1. ADD / AND
        if mnemonic in ("ADD", "AND"):
            op = OP_ADD if mnemonic == "ADD" else OP_AND
            if len(args) != 3:
                raise AssemblyError(idx, raw_line, f"{mnemonic} requiere 3 operandos: {mnemonic} DR, SR1, SR2/imm5.")
            dr = parse_register(args[0])
            sr1 = parse_register(args[1])
            if dr is None or sr1 is None:
                raise AssemblyError(idx, raw_line, f"Registro destino o fuente inválido en {mnemonic}.")

            imm5 = parse_number(args[2])
            if imm5 is not None:
                if imm5 < -16 or imm5 > 15:
                    raise AssemblyError(idx, raw_line, f"Inmediato imm5 ({imm5}) fuera de rango [-16, 15] en {mnemonic}.")
                return (op << 12) | (dr << 9) | (sr1 << 6) | (1 << 5) | (imm5 & 0x1F)
            else:
                sr2 = parse_register(args[2])
                if sr2 is None:
                    raise AssemblyError(idx, raw_line, f"Tercer operando inválido en {mnemonic}: '{args[2]}' (debe ser registro o inmediato #).")
                return (op << 12) | (dr << 9) | (sr1 << 6) | sr2

        # 2. NOT
        elif mnemonic == "NOT":
            if len(args) != 2:
                raise AssemblyError(idx, raw_line, "NOT requiere 2 operandos: NOT DR, SR.")
            dr = parse_register(args[0])
            sr = parse_register(args[1])
            if dr is None or sr is None:
                raise AssemblyError(idx, raw_line, "Registros inválidos en NOT.")
            return (OP_NOT << 12) | (dr << 9) | (sr << 6) | 0x3F

        # 3. BR (BR, BRn, BRz, BRp, BRnz, BRnp, BRzp, BRnzp)
        elif mnemonic.startswith("BR"):
            cond = mnemonic[2:]
            if not cond:
                cond = "NZP"  # BR sin sufijo equivale a BRnzp (incondicional)
            n = 1 if 'N' in cond else 0
            z = 1 if 'Z' in cond else 0
            p = 1 if 'P' in cond else 0
            for ch in cond:
                if ch not in ('N', 'Z', 'P'):
                    raise AssemblyError(idx, raw_line, f"Mnemónico de salto desconocido '{mnemonic}'.")

            if len(args) != 1:
                raise AssemblyError(idx, raw_line, f"{mnemonic} requiere 1 operando (etiqueta o desplazamiento).")
            offset9 = self._resolve_offset(idx, raw_line, args[0], pc, 9)
            return (OP_BR << 12) | (n << 11) | (z << 10) | (p << 9) | offset9

        # 4. LD / LDI / LEA / ST / STI
        elif mnemonic in ("LD", "LDI", "LEA", "ST", "STI"):
            op_map = {"LD": OP_LD, "LDI": OP_LDI, "LEA": OP_LEA, "ST": OP_ST, "STI": OP_STI}
            if len(args) != 2:
                raise AssemblyError(idx, raw_line, f"{mnemonic} requiere 2 operandos: {mnemonic} R, LABEL/offset9.")
            reg = parse_register(args[0])
            if reg is None:
                raise AssemblyError(idx, raw_line, f"Registro inválido en {mnemonic}: '{args[0]}'.")
            offset9 = self._resolve_offset(idx, raw_line, args[1], pc, 9)
            return (op_map[mnemonic] << 12) | (reg << 9) | offset9

        # 5. LDR / STR
        elif mnemonic in ("LDR", "STR"):
            op = OP_LDR if mnemonic == "LDR" else OP_STR
            if len(args) != 3:
                raise AssemblyError(idx, raw_line, f"{mnemonic} requiere 3 operandos: {mnemonic} DR/SR, BaseR, offset6.")
            r = parse_register(args[0])
            base_r = parse_register(args[1])
            if r is None or base_r is None:
                raise AssemblyError(idx, raw_line, f"Registros inválidos en {mnemonic}.")
            offset6 = parse_number(args[2])
            if offset6 is None:
                raise AssemblyError(idx, raw_line, f"Desplazamiento inválido en {mnemonic}: '{args[2]}'. Debe ser número.")
            if offset6 < -32 or offset6 > 31:
                raise AssemblyError(idx, raw_line, f"Desplazamiento offset6 ({offset6}) fuera de rango [-32, 31] en {mnemonic}.")
            return (op << 12) | (r << 9) | (base_r << 6) | (offset6 & 0x3F)

        # 6. JMP
        elif mnemonic == "JMP":
            if len(args) != 1:
                raise AssemblyError(idx, raw_line, "JMP requiere 1 operando: JMP BaseR.")
            base_r = parse_register(args[0])
            if base_r is None:
                raise AssemblyError(idx, raw_line, f"Registro base inválido en JMP: '{args[0]}'.")
            return (OP_JMP << 12) | (base_r << 6)

        # 7. JSR / JSRR
        elif mnemonic == "JSR":
            if len(args) != 1:
                raise AssemblyError(idx, raw_line, "JSR requiere 1 operando (etiqueta o dirección).")
            offset11 = self._resolve_offset(idx, raw_line, args[0], pc, 11)
            return (OP_JSR << 12) | (1 << 11) | offset11

        elif mnemonic == "JSRR":
            if len(args) != 1:
                raise AssemblyError(idx, raw_line, "JSRR requiere 1 operando: JSRR BaseR.")
            base_r = parse_register(args[0])
            if base_r is None:
                raise AssemblyError(idx, raw_line, f"Registro base inválido en JSRR: '{args[0]}'.")
            return (OP_JSR << 12) | (base_r << 6)

        # 8. TRAP
        elif mnemonic == "TRAP":
            if len(args) != 1:
                raise AssemblyError(idx, raw_line, "TRAP requiere 1 vector (ej: TRAP x25).")
            vect = parse_number(args[0])
            if vect is None or vect < 0 or vect > 0xFF:
                raise AssemblyError(idx, raw_line, f"Vector de TRAP inválido '{args[0]}'. Debe estar en [0, 255].")
            return (OP_TRAP << 12) | (vect & 0xFF)

        # 9. RTI
        elif mnemonic == "RTI":
            return OP_RTI << 12

        else:
            raise AssemblyError(idx, raw_line, f"Instrucción desconocida '{mnemonic}'.")

    def write_obj_file(self, filename: str, orig_addr: int, words: List[int]):
        """Escribe el binario estándar .obj de LC-3 en formato big-endian."""
        with open(filename, "wb") as f:
            # Dirección de origen (2 bytes big-endian)
            f.write(orig_addr.to_bytes(2, byteorder="big"))
            # Palabras de código/datos
            for w in words:
                f.write((w & MASK_16).to_bytes(2, byteorder="big"))

    def write_sym_file(self, filename: str, symbols: Dict[str, int]):
        """Escribe el archivo de tabla de símbolos .sym para el depurador."""
        with open(filename, "w", encoding="utf-8") as f:
            f.write("// Symbol table\n")
            f.write("// Scope level 0:\n")
            f.write("//\tSymbol Name       Page Address\n")
            f.write("//\t----------------  ------------\n")
            for sym, addr in sorted(symbols.items(), key=lambda x: x[1]):
                f.write(f"//\t{sym:<16}  x{addr:04X}\n")

    def write_hex_file(self, filename: str, orig_addr: int, words: List[int]):
        """Escribe un archivo en formato hexadecimal de texto (legible o para simuladores como Logisim)."""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# LC-3 HEX DUMP: ORIG x{orig_addr:04X}\n")
            for i, w in enumerate(words):
                f.write(f"x{orig_addr + i:04X}: {w:04X}\n")


def assemble_file(src_path: str, obj_path: str = None, sym_path: str = None, hex_path: str = None) -> Tuple[int, int]:
    """
    Función de utilidad para ensamblar un archivo .asm y generar sus salidas.
    Retorna (orig_addr, total_words).
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
    assembler.write_obj_file(obj_path, orig, words)
    assembler.write_sym_file(sym_path, symbols)

    if hex_path:
        assembler.write_hex_file(hex_path, orig, words)

    return orig, len(words)
