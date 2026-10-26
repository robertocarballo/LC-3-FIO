"""Ensambla texto LC-3 en memoria para SO, archivos, GUI y pruebas.

Posee vocabulario y símbolos de dos pasadas; delega conversiones a isa.
Devuelve origen/palabras y alias de símbolos o AssemblyError; no abre archivos.
"""

import re
from typing import Dict, List, Tuple, Optional
from lc3.domain.isa import (
    OP_BR,
    OP_ADD,
    OP_LD,
    OP_ST,
    OP_JSR,
    OP_AND,
    OP_LDR,
    OP_STR,
    OP_RTI,
    OP_NOT,
    OP_LDI,
    OP_STI,
    OP_JMP,
    OP_LEA,
    OP_TRAP,
    TRAP_GETC,
    TRAP_OUT,
    TRAP_PUTS,
    TRAP_IN,
    TRAP_PUTSP,
    TRAP_HALT,
    to_uint16,
)

# Vocabulario del módulo: registros, expansiones de una palabra y nombres
# reservados compartidos por la clasificación de etiquetas y la codificación.
REGISTERS = {f"R{i}": i for i in range(8)}

PSEUDO_OPS = {
    "GETC": (OP_TRAP << 12) | TRAP_GETC,
    "OUT": (OP_TRAP << 12) | TRAP_OUT,
    "PUTS": (OP_TRAP << 12) | TRAP_PUTS,
    "IN": (OP_TRAP << 12) | TRAP_IN,
    "PUTSP": (OP_TRAP << 12) | TRAP_PUTSP,
    "HALT": (OP_TRAP << 12) | TRAP_HALT,
    "RET": (OP_JMP << 12) | (7 << 6),  # JMP R7
}

RESERVED_WORDS = (
    set(REGISTERS.keys())
    | set(PSEUDO_OPS.keys())
    | {
        "ADD",
        "AND",
        "NOT",
        "BR",
        "BRN",
        "BRZ",
        "BRP",
        "BRNZ",
        "BRNP",
        "BRZP",
        "BRNZP",
        "JMP",
        "JSR",
        "JSRR",
        "LD",
        "LDI",
        "LDR",
        "LEA",
        "ST",
        "STI",
        "STR",
        "TRAP",
        "RTI",
        ".ORIG",
        ".END",
        ".FILL",
        ".BLKW",
        ".STRINGZ",
    }
)


class AssemblyError(Exception):
    """Transporta al invocador el contexto de un rechazo del ensamblador."""

    def __init__(self, line_num: int, line_text: str, message: str):
        """Conserva línea, texto y causa y construye el mensaje de la excepción."""
        self.line_num = line_num
        self.line_text = line_text
        self.message = message
        super().__init__(f"Línea {line_num}: {message}\n  -> {line_text.strip()}")


def parse_number(token: str) -> Optional[int]:
    """Devuelve un entero decimal/hexadecimal/binario o None si no se reconoce.

    Lo usan el parser de ensamblado y consumidores de direcciones; acepta signo
    externo y prefijos #, x/0x o b/0b, sin limitar el rango ni mutar al invocador.
    """
    token = token.strip()
    if not token:
        return None
    try:
        sign = 1
        if token.startswith("-"):
            sign = -1
            token = token[1:]
        elif token.startswith("+"):
            token = token[1:]

        upper = token.upper()
        if upper.startswith("#"):
            return sign * int(token[1:], 10)
        elif upper.startswith("X"):
            return sign * int(token[1:], 16)
        elif upper.startswith("0X"):
            return sign * int(token[2:], 16)
        elif upper.startswith("B"):
            return sign * int(token[1:], 2)
        elif upper.startswith("0B"):
            return sign * int(token[2:], 2)
        elif token.isdigit():
            return sign * int(token, 10)
    except ValueError:
        return None
    return None


def parse_register(token: str) -> Optional[int]:
    """Devuelve el índice R0–R7 sin distinguir mayúsculas, o None si no existe."""
    t = token.strip().upper()
    return REGISTERS.get(t)


def unescape_string(s: str) -> str:
    """Devuelve el texto .STRINGZ con reemplazos de escapes en orden fijo.

    Lo invoca ``assemble`` en ambas pasadas; conserva escapes desconocidos y
    no aplica un analizador general de literales ni modifica la cadena recibida.
    """
    escapes = {
        r"\n": "\n",
        r"\t": "\t",
        r"\r": "\r",
        r"\0": "\0",
        r"\"": '"',
        r"\\": "\\",
    }
    for k, v in escapes.items():
        s = s.replace(k, v)
    return s


def tokenize_line(line: str) -> List[str]:
    """Devuelve tokens de una línea para las dos pasadas de ``assemble``.

    Recorta sólo comentarios ``;`` fuera de comillas; ``#`` sigue disponible
    para números. Delega la separación por blancos/comas en una expresión
    regular que conserva cadenas entre comillas sin validar toda su sintaxis.
    """
    # Eliminar comentarios que no estén dentro de comillas
    cleaned = []
    in_quotes = False
    escape = False
    for char in line:
        if char == '"' and not escape:
            in_quotes = not in_quotes
        elif char == ";" and not in_quotes:
            break
        cleaned.append(char)
        if char == "\\" and not escape:
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
    """Posee el estado reutilizable del ensamblado, no el de la CPU.

    CLI, GUI, SO y pruebas solicitan palabras mediante ``assemble``. Los helpers
    de instancia resuelven símbolos y codifican en memoria. ``symbols`` conserva nombres sensibles a mayúsculas,
    ``orig_addr`` el origen. Las palabras emitidas pertenecen al resultado.
    Un fallo puede dejar ese estado parcialmente actualizado.
    """

    def __init__(self):
        """Crea tablas propias vacías y un origen aún no establecido."""
        self.symbols: Dict[str, int] = {}
        self.orig_addr: Optional[int] = None

    def assemble(self, source_text: str) -> Tuple[int, List[int], Dict[str, int]]:
        """Transforma fuente en origen, palabras y la tabla interna de símbolos.

        Invocado por los consumidores de esta clase, reinicia sus campos antes
        de tokenizar; una pasada fija etiquetas/tamaños y otra delega en los
        parsers y codificador para emitir palabras. .STRINGZ usa el byte bajo
        de cada carácter y .BLKW emite ceros.

        Returns:
            Tuple[int, List[int], Dict[str, int]]: Origen, lista nueva de palabras
            y alias de ``self.symbols``; otro ensamblado vacía y cambia ese mismo
            diccionario, incluso si termina fallando.

        Raises:
            AssemblyError: Directiva, etiqueta, operando o rango rechazado por
                las comprobaciones implementadas; no restaura el estado previo.
        """
        lines = source_text.splitlines()
        self.symbols.clear()
        self.orig_addr = None

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
            has_colon = first_token.endswith(":")
            potential_label = first_token[:-1] if has_colon else first_token

            is_reserved = (
                upper_first in RESERVED_WORDS
                or upper_first.startswith("BR")
                or upper_first.startswith(".")
            )

            if has_colon or (
                not is_reserved
                and parse_register(first_token) is None
                and parse_number(first_token) is None
            ):
                label = potential_label
                tokens = tokens[1:]

            if label:
                clean_label = label.strip()
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", clean_label):
                    raise AssemblyError(
                        idx,
                        raw_line,
                        f"Nombre de etiqueta inválido '{clean_label}'. Debe comenzar con letra o guión bajo.",
                    )
                if (
                    clean_label.upper() in RESERVED_WORDS
                    or clean_label.upper().startswith("BR")
                ):
                    raise AssemblyError(
                        idx,
                        raw_line,
                        f"La etiqueta '{clean_label}' es una palabra reservada o mnemónico de la ISA.",
                    )
                if clean_label in self.symbols:
                    raise AssemblyError(
                        idx, raw_line, f"Etiqueta duplicada '{clean_label}'."
                    )

            if not tokens:
                # Línea que solo tenía etiqueta
                if label:
                    if self.orig_addr is None:
                        raise AssemblyError(
                            idx,
                            raw_line,
                            "La etiqueta aparece antes de la directiva .ORIG.",
                        )
                    self.symbols[label] = current_pc
                    parsed_lines.append((idx, raw_line, label, None, []))
                continue

            mnemonic = tokens[0].upper()
            args = tokens[1:]

            if mnemonic == ".ORIG":
                if self.orig_addr is not None:
                    raise AssemblyError(
                        idx, raw_line, "Múltiples directivas .ORIG encontradas."
                    )
                if not args:
                    raise AssemblyError(
                        idx,
                        raw_line,
                        "La directiva .ORIG requiere una dirección (ej: .ORIG x3000).",
                    )
                addr = parse_number(args[0])
                if addr is None or addr < 0 or addr > 0xFFFF:
                    raise AssemblyError(
                        idx, raw_line, f"Dirección .ORIG inválida '{args[0]}'."
                    )
                self.orig_addr = addr
                current_pc = addr
                if label:
                    self.symbols[label] = current_pc
                parsed_lines.append((idx, raw_line, label, mnemonic, args))
                continue

            if self.orig_addr is None:
                raise AssemblyError(
                    idx, raw_line, "El programa debe iniciar con la directiva .ORIG."
                )

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
                    raise AssemblyError(
                        idx,
                        raw_line,
                        ".BLKW requiere una cantidad de palabras (ej: .BLKW #10).",
                    )
                count = parse_number(args[0])
                if count is None or count <= 0:
                    raise AssemblyError(
                        idx, raw_line, f"Cantidad inválida para .BLKW '{args[0]}'."
                    )
                line_size = count
            elif mnemonic == ".STRINGZ":
                if not args:
                    raise AssemblyError(
                        idx, raw_line, ".STRINGZ requiere una cadena entre comillas."
                    )
                joined = " ".join(args)
                if not (joined.startswith('"') and joined.endswith('"')):
                    raise AssemblyError(
                        idx,
                        raw_line,
                        ".STRINGZ requiere una cadena encerrada en comillas dobles.",
                    )
                content = unescape_string(joined[1:-1])
                line_size = len(content) + 1  # Incluye el carácter nulo terminador '\0'

            parsed_lines.append(
                (idx, raw_line, label, mnemonic, args, current_pc, line_size)
            )
            current_pc += line_size
            if current_pc > 0x10000:
                raise AssemblyError(
                    idx,
                    raw_line,
                    "El programa excede el tamaño de memoria de 16 bits de la LC-3.",
                )

        if self.orig_addr is None:
            raise AssemblyError(
                1, "", "No se encontró la directiva .ORIG en el archivo."
            )
        if not saw_end:
            raise AssemblyError(
                len(lines), "", "Falta la directiva .END al final del archivo."
            )

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
                    raise AssemblyError(
                        idx, raw_line, ".FILL requiere un valor numérico o etiqueta."
                    )
                val = parse_number(args[0])
                if val is None:
                    # Debe ser una etiqueta
                    if args[0] not in self.symbols:
                        raise AssemblyError(
                            idx, raw_line, f"Símbolo no definido '{args[0]}' en .FILL."
                        )
                    val = self.symbols[args[0]]
                words.append(to_uint16(val))
                continue

            elif mnemonic == ".BLKW":
                count = parse_number(args[0])
                for i in range(count):
                    words.append(0)
                continue

            elif mnemonic == ".STRINGZ":
                joined = " ".join(args)
                content = unescape_string(joined[1:-1])
                for i, ch in enumerate(content):
                    words.append(ord(ch) & 0xFF)
                words.append(0)  # Nulo terminador
                continue

            # Pseudo-instrucciones TRAP y RET
            if mnemonic in PSEUDO_OPS:
                code = PSEUDO_OPS[mnemonic]
                words.append(code)
                continue

            # Instrucciones de la ISA
            code = self._encode_instruction(idx, raw_line, mnemonic, args, pc)
            words.append(code)

        return self.orig_addr, words, self.symbols

    def _resolve_offset(
        self, idx: int, raw_line: str, token: str, pc: int, bit_count: int
    ) -> int:
        """Resuelve para el codificador un campo relativo sin modificar símbolos.

        Un número representa el desplazamiento literal; una etiqueta se busca
        en la tabla de esta instancia y resta PC+1, sin ajuste circular.

        Returns:
            int: Desplazamiento representado en ``bit_count`` bits.

        Raises:
            AssemblyError: Símbolo ausente o desplazamiento fuera del rango
                con signo; incluye ``idx`` y ``raw_line`` como contexto.
        """
        target = parse_number(token)
        if target is None:
            if token not in self.symbols:
                raise AssemblyError(
                    idx, raw_line, f"Etiqueta o símbolo no definido: '{token}'."
                )
            target = self.symbols[token]
            offset = target - (pc + 1)
        else:
            # Si se dio directamente un número, puede ser un desplazamiento literal
            offset = target

        min_val = -(1 << (bit_count - 1))
        max_val = (1 << (bit_count - 1)) - 1
        if offset < min_val or offset > max_val:
            raise AssemblyError(
                idx,
                raw_line,
                f"Desplazamiento PCoffset{bit_count} fuera de rango: {offset}. "
                f"Rango permitido: [{min_val}, {max_val}] (destino x{target:04X}, PC x{pc:04X}).",
            )
        mask = (1 << bit_count) - 1
        return offset & mask

    def _encode_instruction(
        self, idx: int, raw_line: str, mnemonic: str, args: List[str], pc: int
    ) -> int:
        """Devuelve una palabra ISA para la segunda pasada de ``assemble``.

        Consulta la tabla de esta instancia mediante ``_resolve_offset`` y
        delega números y registros en los parsers del módulo, sin escribir
        palabras ni archivos. Las comprobaciones dependen del mnemónico:
        RTI, por ejemplo, se emite sin comprobar los operandos sobrantes.

        Raises:
            AssemblyError: Mnemónico, cantidad de operandos, registro, inmediato
                o destino rechazado por la rama correspondiente.
        """
        # 1. ADD / AND
        if mnemonic in ("ADD", "AND"):
            op = OP_ADD if mnemonic == "ADD" else OP_AND
            if len(args) != 3:
                raise AssemblyError(
                    idx,
                    raw_line,
                    f"{mnemonic} requiere 3 operandos: {mnemonic} DR, SR1, SR2/imm5.",
                )
            dr = parse_register(args[0])
            sr1 = parse_register(args[1])
            if dr is None or sr1 is None:
                raise AssemblyError(
                    idx, raw_line, f"Registro destino o fuente inválido en {mnemonic}."
                )

            imm5 = parse_number(args[2])
            if imm5 is not None:
                if imm5 < -16 or imm5 > 15:
                    raise AssemblyError(
                        idx,
                        raw_line,
                        f"Inmediato imm5 ({imm5}) fuera de rango [-16, 15] en {mnemonic}.",
                    )
                return (op << 12) | (dr << 9) | (sr1 << 6) | (1 << 5) | (imm5 & 0x1F)
            else:
                sr2 = parse_register(args[2])
                if sr2 is None:
                    raise AssemblyError(
                        idx,
                        raw_line,
                        f"Tercer operando inválido en {mnemonic}: '{args[2]}' (debe ser registro o inmediato #).",
                    )
                return (op << 12) | (dr << 9) | (sr1 << 6) | sr2

        # 2. NOT
        elif mnemonic == "NOT":
            if len(args) != 2:
                raise AssemblyError(
                    idx, raw_line, "NOT requiere 2 operandos: NOT DR, SR."
                )
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
            n = 1 if "N" in cond else 0
            z = 1 if "Z" in cond else 0
            p = 1 if "P" in cond else 0
            for ch in cond:
                if ch not in ("N", "Z", "P"):
                    raise AssemblyError(
                        idx, raw_line, f"Mnemónico de salto desconocido '{mnemonic}'."
                    )

            if len(args) != 1:
                raise AssemblyError(
                    idx,
                    raw_line,
                    f"{mnemonic} requiere 1 operando (etiqueta o desplazamiento).",
                )
            offset9 = self._resolve_offset(idx, raw_line, args[0], pc, 9)
            return (OP_BR << 12) | (n << 11) | (z << 10) | (p << 9) | offset9

        # 4. LD / LDI / LEA / ST / STI
        elif mnemonic in ("LD", "LDI", "LEA", "ST", "STI"):
            op_map = {
                "LD": OP_LD,
                "LDI": OP_LDI,
                "LEA": OP_LEA,
                "ST": OP_ST,
                "STI": OP_STI,
            }
            if len(args) != 2:
                raise AssemblyError(
                    idx,
                    raw_line,
                    f"{mnemonic} requiere 2 operandos: {mnemonic} R, LABEL/offset9.",
                )
            reg = parse_register(args[0])
            if reg is None:
                raise AssemblyError(
                    idx, raw_line, f"Registro inválido en {mnemonic}: '{args[0]}'."
                )
            offset9 = self._resolve_offset(idx, raw_line, args[1], pc, 9)
            return (op_map[mnemonic] << 12) | (reg << 9) | offset9

        # 5. LDR / STR
        elif mnemonic in ("LDR", "STR"):
            op = OP_LDR if mnemonic == "LDR" else OP_STR
            if len(args) != 3:
                raise AssemblyError(
                    idx,
                    raw_line,
                    f"{mnemonic} requiere 3 operandos: {mnemonic} DR/SR, BaseR, offset6.",
                )
            r = parse_register(args[0])
            base_r = parse_register(args[1])
            if r is None or base_r is None:
                raise AssemblyError(
                    idx, raw_line, f"Registros inválidos en {mnemonic}."
                )
            offset6 = parse_number(args[2])
            if offset6 is None:
                raise AssemblyError(
                    idx,
                    raw_line,
                    f"Desplazamiento inválido en {mnemonic}: '{args[2]}'. Debe ser número.",
                )
            if offset6 < -32 or offset6 > 31:
                raise AssemblyError(
                    idx,
                    raw_line,
                    f"Desplazamiento offset6 ({offset6}) fuera de rango [-32, 31] en {mnemonic}.",
                )
            return (op << 12) | (r << 9) | (base_r << 6) | (offset6 & 0x3F)

        # 6. JMP
        elif mnemonic == "JMP":
            if len(args) != 1:
                raise AssemblyError(
                    idx, raw_line, "JMP requiere 1 operando: JMP BaseR."
                )
            base_r = parse_register(args[0])
            if base_r is None:
                raise AssemblyError(
                    idx, raw_line, f"Registro base inválido en JMP: '{args[0]}'."
                )
            return (OP_JMP << 12) | (base_r << 6)

        # 7. JSR / JSRR
        elif mnemonic == "JSR":
            if len(args) != 1:
                raise AssemblyError(
                    idx, raw_line, "JSR requiere 1 operando (etiqueta o dirección)."
                )
            offset11 = self._resolve_offset(idx, raw_line, args[0], pc, 11)
            return (OP_JSR << 12) | (1 << 11) | offset11

        elif mnemonic == "JSRR":
            if len(args) != 1:
                raise AssemblyError(
                    idx, raw_line, "JSRR requiere 1 operando: JSRR BaseR."
                )
            base_r = parse_register(args[0])
            if base_r is None:
                raise AssemblyError(
                    idx, raw_line, f"Registro base inválido en JSRR: '{args[0]}'."
                )
            return (OP_JSR << 12) | (base_r << 6)

        # 8. TRAP
        elif mnemonic == "TRAP":
            if len(args) != 1:
                raise AssemblyError(
                    idx, raw_line, "TRAP requiere 1 vector (ej: TRAP x25)."
                )
            vect = parse_number(args[0])
            if vect is None or vect < 0 or vect > 0xFF:
                raise AssemblyError(
                    idx,
                    raw_line,
                    f"Vector de TRAP inválido '{args[0]}'. Debe estar en [0, 255].",
                )
            return (OP_TRAP << 12) | (vect & 0xFF)

        # 9. RTI
        elif mnemonic == "RTI":
            return OP_RTI << 12

        else:
            raise AssemblyError(idx, raw_line, f"Instrucción desconocida '{mnemonic}'.")
