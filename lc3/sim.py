"""Máquina virtual y motor de simulación de la CPU para la arquitectura LC-3.

Responsabilidad:
    Emular el procesador LC-3 ejecutando el ciclo fetch-decode-execute sobre un espacio de
    memoria de 64K palabras y 8 registros generales (R0–R7), actualizando los códigos de condición,
    gestionando llamadas TRAP por hardware y canalizando E/S mediante registros mapeados en memoria (MMIO).
"""

import sys
import os
import time
from typing import Optional, Dict
from .core import (
    MEMORY_SIZE, MASK_16, NUM_REGISTERS,
    FL_POS, FL_ZRO, FL_NEG,
    OP_BR, OP_ADD, OP_LD, OP_ST, OP_JSR, OP_AND, OP_LDR, OP_STR,
    OP_RTI, OP_NOT, OP_LDI, OP_STI, OP_JMP, OP_RES, OP_LEA, OP_TRAP,
    TRAP_GETC, TRAP_OUT, TRAP_PUTS, TRAP_IN, TRAP_PUTSP, TRAP_HALT,
    MR_KBSR, MR_KBDR, MR_DSR, MR_DDR, MR_MCR,
    sign_extend, to_uint16, to_int16
)
from .os_image import get_os_image

# Soporte para entrada de teclado no bloqueante en Windows
try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


class LC3Simulator:
    """Máquina Virtual que emula el procesador y subsistema de memoria de la arquitectura LC-3.

    Attributes:
        memory (List[int]): Espacio direccionable de 65,536 palabras de 16 bits sin signo.
        reg (List[int]): Banco de 8 registros de propósito general (R0 a R7).
        pc (int): Contador de programa (Program Counter), típicamente inicializado en x3000.
        cond (int): Flags de condición del PSR (FL_POS, FL_ZRO, FL_NEG).
        running (bool): Estado del reloj de la CPU (True mientras el procesador esté activo).
        instruction_count (int): Contador acumulativo de instrucciones ejecutadas.
        symbols (Dict[int, str]): Tabla de símbolos {direccion: etiqueta} para resolución en desensamblado.
    """

    def __init__(self):
        self.memory = [0] * MEMORY_SIZE
        self.reg = [0] * NUM_REGISTERS
        self.pc = 0x3000
        self.cond = FL_ZRO
        self.running = False
        self.instruction_count = 0
        self.symbols: Dict[int, str] = {}  # Mapeo {direccion: nombre_etiqueta}

        # Callbacks opcionales para interfaz gráfica o redirección de E/S
        self.output_fn = None
        self.input_fn = None
        self.has_input_fn = None
        self.kbsr_poll_fn = None

        # Modo de ejecución de TRAP: si es True, se ejecuta el código del SO en memoria
        self.os_traps_enabled = True
        self.os_symbols = {}
        self._halt_saved_regs = None
        self._halt_saved_cond = None

        # Inicializar registros MMIO
        self.memory[MR_DSR] = 0x8000  # Pantalla lista
        self.memory[MR_MCR] = 0x8000  # Reloj habilitado

        # Cargar el Sistema Operativo (Tabla de Vectores y manejadores TRAP)
        self.load_os()

    def load_os(self):
        """Carga en memoria la imagen binaria del Sistema Operativo LC-3 y su tabla de vectores."""
        os_mem, os_sym = get_os_image()
        self.os_symbols = os_sym
        for addr, val in os_mem.items():
            self.memory[addr] = val
        for addr, name in os_sym.items():
            if addr not in self.symbols:
                self.symbols[addr] = name

    def _output_text(self, text: str):
        """Envía texto a la consola o al callback configurado de la GUI."""
        if self.output_fn:
            self.output_fn(text)
        else:
            sys.stdout.write(text)
            sys.stdout.flush()

    def reset(self, start_pc: int = 0x3000):
        """Restablece el estado de los registros, banderas y PC a los valores iniciales.

        Args:
            start_pc (int, optional): Dirección de memoria en la que comenzará el PC. Por defecto x3000.
        """
        self.reg = [0] * NUM_REGISTERS
        self.pc = start_pc & MASK_16
        self.cond = FL_ZRO
        self.running = False
        self.instruction_count = 0
        self._halt_saved_regs = None
        self._halt_saved_cond = None
        self.memory[MR_DSR] = 0x8000
        self.memory[MR_MCR] = 0x8000
        if self.os_traps_enabled:
            self.load_os()

    def load_obj(self, filename: str) -> int:
        """Carga un archivo binario ejecutable .obj estándar en el espacio de memoria.

        Lee la cabecera big-endian de 2 bytes para determinar la dirección de origen (.ORIG)
        y almacena secuencialmente las palabras subsiguientes.

        Args:
            filename (str): Ruta del binario .obj en el sistema de archivos.

        Returns:
            int: Dirección inicial de carga (.ORIG) en la que se posiciona el PC.

        Raises:
            ValueError: Si el archivo está vacío o posee un tamaño inferior a 2 bytes.
            OSError: Si ocurren errores de acceso o lectura en disco.
        """
        with open(filename, "rb") as f:
            data = f.read()

        if len(data) < 2:
            raise ValueError(f"El archivo {filename} está vacío o es inválido.")

        # Dirección de origen
        orig = int.from_bytes(data[0:2], byteorder="big")
        address = orig

        for i in range(2, len(data), 2):
            if i + 1 < len(data):
                val = int.from_bytes(data[i:i+2], byteorder="big")
                self.memory[address & MASK_16] = val
                address += 1

        self.pc = orig
        return orig

    def load_sym(self, filename: str):
        """Carga una tabla de símbolos .sym para permitir resolución simbólica en depuración.

        Args:
            filename (str): Ruta del archivo .sym en disco.
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
                if not line or line.startswith("---") or "Symbol Name" in line or "Scope" in line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    addr_str = parts[1].replace("x", "").replace("X", "")
                    try:
                        addr = int(addr_str, 16)
                        self.symbols[addr] = name
                    except ValueError:
                        pass

    def update_flags(self, reg_num: int):
        """Actualiza los flags de condición (N, Z, P) en función del valor con signo del registro indicado.

        Args:
            reg_num (int): Índice del registro modificado [0..7].
        """
        val = to_int16(self.reg[reg_num])
        if val == 0:
            self.cond = FL_ZRO
        elif val > 0:
            self.cond = FL_POS
        else:
            self.cond = FL_NEG

    def _read_char(self) -> int:
        """Lee un carácter del usuario sin esperar salto de línea si es posible."""
        if self.input_fn:
            return self.input_fn()
        if HAS_MSVCRT:
            ch = msvcrt.getch()
            # En Windows con msvcrt, \r (Enter) suele devolverse como 13
            if ch == b'\r':
                return 10  # \n estándar
            return ord(ch)
        else:
            ch = sys.stdin.read(1)
            return ord(ch) if ch else 0

    def mem_read(self, address: int) -> int:
        """Lee una palabra de 16 bits de la memoria, interceptando accesos a registros MMIO.

        Si la dirección corresponde a KBSR (xFE00), sondea el teclado y actualiza el bit 15.
        Si corresponde a KBDR (xFE02), retorna el carácter ASCII y limpia el bit 15 de KBSR.

        Args:
            address (int): Dirección de memoria solicitada.

        Returns:
            int: Valor de 16 bits almacenado o provisto por el periférico MMIO.
        """
        address &= MASK_16

        # Registro de estado de teclado (KBSR)
        if address == MR_KBSR:
            has_input = False
            if self.has_input_fn:
                has_input = bool(self.has_input_fn())
                self.memory[MR_KBSR] = 0x8000 if has_input else 0x0000
            elif HAS_MSVCRT:
                if msvcrt.kbhit():
                    has_input = True
                    self.memory[MR_KBSR] = 0x8000
                else:
                    self.memory[MR_KBSR] = 0x0000
                    time.sleep(0.001)
            else:
                self.memory[MR_KBSR] = 0x0000

            if getattr(self, "kbsr_poll_fn", None):
                self.kbsr_poll_fn(has_input)

            return self.memory[MR_KBSR]

        # Registro de datos de teclado (KBDR)
        elif address == MR_KBDR:
            if self.input_fn:
                ch = self.input_fn()
                self.memory[MR_KBDR] = ch & 0xFF
            elif HAS_MSVCRT:
                ch = self._read_char()
                self.memory[MR_KBDR] = ch & 0xFF
            val = self.memory[MR_KBDR]
            self.memory[MR_KBSR] = 0x0000  # Limpiar bandera de teclado al leer datos
            if getattr(self, "kbsr_poll_fn", None):
                self.kbsr_poll_fn(True)
            return val

        elif address == MR_DSR:
            return 0x8000  # Siempre listo para imprimir

        return self.memory[address]

    def mem_write(self, address: int, val: int):
        """Escribe una palabra de 16 bits en la memoria, interceptando registros de control MMIO.

        Si la dirección es DDR (xFE06), emite el carácter a la consola o al callback de salida.
        Si la dirección es MCR (xFFFE), comprueba el bit 15 para detener el reloj de la CPU (HALT).

        Args:
            address (int): Dirección de memoria destino.
            val (int): Valor de 16 bits a persistir.
        """
        address &= MASK_16
        val &= MASK_16

        if address == MR_DDR:
            # Imprime el carácter en consola
            self._output_text(chr(val & 0xFF))
            self.memory[MR_DDR] = val
        elif address == MR_MCR:
            if not (val & 0x8000):
                self.running = False
                # Restaurar registros y flags de condición del usuario tras HALT
                if self._halt_saved_regs is not None:
                    self.reg = list(self._halt_saved_regs)
                    self.cond = self._halt_saved_cond
                    self._halt_saved_regs = None
                    self._halt_saved_cond = None
            self.memory[MR_MCR] = val
        else:
            self.memory[address] = val

    def handle_trap(self, trapvect: int):
        """Ejecuta una llamada al sistema TRAP mediante emulación directa o linkage por hardware.

        Args:
            trapvect (int): Vector de interrupción de 8 bits (e.g., x20 para GETC, x25 para HALT).
        """
        if trapvect == TRAP_GETC:
            ch = self._read_char()
            self.reg[0] = ch & 0xFF

        elif trapvect == TRAP_OUT:
            char = chr(self.reg[0] & 0xFF)
            self._output_text(char)

        elif trapvect == TRAP_PUTS:
            curr_addr = self.reg[0] & MASK_16
            chars = []
            while True:
                c = self.memory[curr_addr] & 0xFF
                if c == 0:
                    break
                chars.append(chr(c))
                curr_addr = (curr_addr + 1) & MASK_16
            self._output_text("".join(chars))

        elif trapvect == TRAP_IN:
            self._output_text("Input a character: ")
            ch = self._read_char()
            self._output_text(chr(ch))
            self.reg[0] = ch & 0xFF

        elif trapvect == TRAP_PUTSP:
            curr_addr = self.reg[0] & MASK_16
            chars = []
            while True:
                word = self.memory[curr_addr]
                c1 = word & 0xFF
                if c1 == 0:
                    break
                chars.append(chr(c1))
                c2 = (word >> 8) & 0xFF
                if c2 == 0:
                    break
                chars.append(chr(c2))
                curr_addr = (curr_addr + 1) & MASK_16
            self._output_text("".join(chars))

        elif trapvect == TRAP_HALT:
            self._output_text("\n*** HALT: Procesador detenido por instrucción TRAP x25 ***\n")
            self.running = False

        else:
            # Trap de vector genérico: salto por tabla de vectores si estuviera cargada
            vector_addr = self.mem_read(trapvect)
            if vector_addr != 0:
                self.pc = vector_addr
            else:
                print(f"[Aviso] TRAP x{trapvect:02X} no implementado.")

    def step(self) -> bool:
        """Ejecuta un ciclo completo de instrucción (Fetch -> Decode -> Execute).

        Returns:
            bool: True si el procesador continúa en ejecución; False si se detuvo (HALT o error).
        """
        # Fetch
        instr = self.mem_read(self.pc)
        curr_pc = self.pc
        self.pc = (self.pc + 1) & MASK_16

        # Decode
        op = (instr >> 12) & 0xF

        # Execute
        if op == OP_ADD:
            dr = (instr >> 9) & 0x7
            sr1 = (instr >> 6) & 0x7
            if (instr >> 5) & 1:
                imm5 = sign_extend(instr & 0x1F, 5)
                self.reg[dr] = to_uint16(self.reg[sr1] + imm5)
            else:
                sr2 = instr & 0x7
                self.reg[dr] = to_uint16(self.reg[sr1] + self.reg[sr2])
            self.update_flags(dr)

        elif op == OP_AND:
            dr = (instr >> 9) & 0x7
            sr1 = (instr >> 6) & 0x7
            if (instr >> 5) & 1:
                imm5 = sign_extend(instr & 0x1F, 5)
                self.reg[dr] = to_uint16(self.reg[sr1] & imm5)
            else:
                sr2 = instr & 0x7
                self.reg[dr] = to_uint16(self.reg[sr1] & self.reg[sr2])
            self.update_flags(dr)

        elif op == OP_NOT:
            dr = (instr >> 9) & 0x7
            sr = (instr >> 6) & 0x7
            self.reg[dr] = to_uint16(~self.reg[sr])
            self.update_flags(dr)

        elif op == OP_BR:
            cond_flags = (instr >> 9) & 0x7
            if cond_flags & self.cond:
                offset9 = sign_extend(instr & 0x1FF, 9)
                self.pc = (self.pc + offset9) & MASK_16

        elif op == OP_JMP:
            base_r = (instr >> 6) & 0x7
            self.pc = self.reg[base_r] & MASK_16

        elif op == OP_JSR:
            self.reg[7] = self.pc
            if (instr >> 11) & 1:
                offset11 = sign_extend(instr & 0x7FF, 11)
                self.pc = (self.pc + offset11) & MASK_16
            else:
                base_r = (instr >> 6) & 0x7
                self.pc = self.reg[base_r] & MASK_16

        elif op == OP_LD:
            dr = (instr >> 9) & 0x7
            offset9 = sign_extend(instr & 0x1FF, 9)
            target = (self.pc + offset9) & MASK_16
            self.reg[dr] = self.mem_read(target)
            self.update_flags(dr)

        elif op == OP_LDI:
            dr = (instr >> 9) & 0x7
            offset9 = sign_extend(instr & 0x1FF, 9)
            target = (self.pc + offset9) & MASK_16
            indirect_addr = self.mem_read(target)
            self.reg[dr] = self.mem_read(indirect_addr)
            self.update_flags(dr)

        elif op == OP_LDR:
            dr = (instr >> 9) & 0x7
            base_r = (instr >> 6) & 0x7
            offset6 = sign_extend(instr & 0x3F, 6)
            target = (self.reg[base_r] + offset6) & MASK_16
            self.reg[dr] = self.mem_read(target)
            self.update_flags(dr)

        elif op == OP_LEA:
            dr = (instr >> 9) & 0x7
            offset9 = sign_extend(instr & 0x1FF, 9)
            self.reg[dr] = (self.pc + offset9) & MASK_16
            self.update_flags(dr)

        elif op == OP_ST:
            sr = (instr >> 9) & 0x7
            offset9 = sign_extend(instr & 0x1FF, 9)
            target = (self.pc + offset9) & MASK_16
            self.mem_write(target, self.reg[sr])

        elif op == OP_STI:
            sr = (instr >> 9) & 0x7
            offset9 = sign_extend(instr & 0x1FF, 9)
            target = (self.pc + offset9) & MASK_16
            indirect_addr = self.mem_read(target)
            self.mem_write(indirect_addr, self.reg[sr])

        elif op == OP_STR:
            sr = (instr >> 9) & 0x7
            base_r = (instr >> 6) & 0x7
            offset6 = sign_extend(instr & 0x3F, 6)
            target = (self.reg[base_r] + offset6) & MASK_16
            self.mem_write(target, self.reg[sr])

        elif op == OP_TRAP:
            trapvect = instr & 0xFF
            self.reg[7] = self.pc
            if self.os_traps_enabled:
                if trapvect == TRAP_HALT:
                    self._halt_saved_regs = list(self.reg)
                    self._halt_saved_cond = self.cond
                vector_addr = self.mem_read(trapvect)
                if vector_addr != 0:
                    self.pc = vector_addr
                else:
                    self.handle_trap(trapvect)
            else:
                self.handle_trap(trapvect)

        elif op == OP_RTI:
            # En modo simulador educativo simple no interrumpe
            pass

        elif op == OP_RES:
            print(f"[Error] Código de operación reservado/inválido en x{curr_pc:04X} (x{instr:04X})")
            self.running = False

        self.instruction_count += 1
        return self.running

    def run(self, max_steps: Optional[int] = None) -> int:
        """Ejecuta continuamente el ciclo de instrucciones hasta HALT o hasta alcanzar un límite.

        Args:
            max_steps (Optional[int], optional): Número máximo de ciclos antes de pausar.

        Returns:
            int: Número total de instrucciones ejecutadas.
        """
        self.running = True
        try:
            while self.running:
                if max_steps and self.instruction_count >= max_steps:
                    print(f"\n[Aviso] Se alcanzó el límite máximo de pasos ({max_steps}).")
                    break
                self.step()
        except KeyboardInterrupt:
            print("\n[Interrupción] Ejecución pausada por el usuario (Ctrl+C).")
            self.running = False
        return self.instruction_count
