"""Dominio de CPU, memoria y MMIO invocado por CLI, depurador, GUI y pruebas.

La máquina posee registros, memoria, símbolos y snapshots HALT; recibe el puerto
HostIO y una imagen SO ya construida de bootstrap, sin acceder a archivos ni
terminales. Conserva plantillas privadas del SO y delega E/S al puerto o a los
callbacks instalados por presentación. Las excepciones de callbacks interrumpen
los efectos en curso. Los breakpoints pertenecen a presentación.
"""

from typing import Dict, Iterable, Optional, Tuple

from lc3.domain.isa import (
    MEMORY_SIZE,
    MASK_16,
    NUM_REGISTERS,
    FL_POS,
    FL_ZRO,
    FL_NEG,
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
    OP_RES,
    OP_LEA,
    OP_TRAP,
    TRAP_GETC,
    TRAP_OUT,
    TRAP_PUTS,
    TRAP_IN,
    TRAP_PUTSP,
    TRAP_HALT,
    MR_KBSR,
    MR_KBDR,
    MR_DSR,
    MR_DDR,
    MR_MCR,
    sign_extend,
    to_uint16,
    to_int16,
)
from lc3.domain.ports import HostIO


class LC3Simulator:
    """Mantiene estado LC-3 y ejecuta ISA educativa, TRAP nativo o SO en memoria.

    Posee copias privadas de la imagen recibida; os_symbols es un mapa público
    independiente que load_os sustituye al recargar. Los cuatro callbacks son
    overrides opcionales de presentación y sus errores se propagan.
    """

    def __init__(self, io: HostIO, os_image: Tuple[Dict[int, int], Dict[int, str]]):
        """Inicializa CPU/MMIO y carga una copia de la imagen SO proporcionada.

        Bootstrap entrega el puerto y los mapas de palabras/símbolos del SO.
        La máquina no obtiene imágenes ni instala una lectura bloqueante como
        input_fn; conserva el puerto para las operaciones sin override.
        """
        self._io = io
        self._os_memory_template = dict(os_image[0])
        self._os_symbols_template = dict(os_image[1])
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
        """Recarga plantillas propias sin sobrescribir etiquetas existentes.

        Constructor y reset copian palabras directamente y crean os_symbols
        fresco; mutar ese mapa público no altera la siguiente recarga. Sólo
        añade nombres a symbols cuando la dirección todavía no tiene etiqueta.
        """
        self.os_symbols = dict(self._os_symbols_template)
        for addr, val in self._os_memory_template.items():
            self.memory[addr] = val
        for addr, name in self.os_symbols.items():
            if addr not in self.symbols:
                self.symbols[addr] = name

    def _output_text(self, text: str):
        """Entrega texto desde TRAP/DDR a output_fn o al puerto del anfitrión."""
        if self.output_fn is not None:
            self.output_fn(text)
        else:
            self._io.write_text(text)

    def reset(self, start_pc: int = 0x3000):
        """Reinicia CPU/MMIO y snapshots, conserva memoria de usuario y símbolos.

        CLI/GUI/depurador indican el PC inicial; sólo recarga SO si
        os_traps_enabled. No elimina callbacks ni tablas de símbolos completas.
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

    def load_words(self, orig_addr: int, words: Iterable[int]) -> int:
        """Carga palabras directamente para adaptadores y editor, sin efectos MMIO.

        Consume words una vez, enmascara cada palabra y envuelve las direcciones
        a 16 bits. El origen válido, de 0 a 65535, procede del ensamblador o de
        una cabecera OBJ; no se valida de nuevo. No resetea CPU ni símbolos y
        fija PC al origen después de consumir el iterable.

        Returns:
            int: Origen recibido, también para una secuencia vacía.
        """
        for offset, word in enumerate(words):
            self.memory[(orig_addr + offset) & MASK_16] = word & MASK_16
        self.pc = orig_addr
        return orig_addr

    def update_flags(self, reg_num: int):
        """Actualiza cond de esta CPU desde reg_num; step y editores lo invocan."""
        val = to_int16(self.reg[reg_num])
        if val == 0:
            self.cond = FL_ZRO
        elif val > 0:
            self.cond = FL_POS
        else:
            self.cond = FL_NEG

    def _read_char(self) -> int:
        """Devuelve carácter para TRAP nativo desde input_fn o HostIO.read_char.

        El puerto puede bloquear; la lectura MMIO sin callback usa read_key,
        cuya capacidad puede no estar disponible, en lugar de esta ruta.
        """
        if self.input_fn is not None:
            return self.input_fn()
        return self._io.read_char()

    def mem_read(self, address: int) -> int:
        """Lee palabra y ejecuta efectos MMIO para step y consumidores de memoria.

        KBSR consulta callback o puerto, almacena estado y luego notifica. Un
        callback instalado prevalece aunque no tenga entrada; None del puerto
        equivale a no disponible. KBDR consume input_fn (debe devolver int) o
        read_key (None conserva dato); guarda byte, limpia KBSR y notifica True.
        DSR devuelve siempre x8000. Las excepciones se propagan sin completar
        efectos restantes.
        """
        address &= MASK_16

        # Registro de estado de teclado (KBSR)
        if address == MR_KBSR:
            if self.has_input_fn is not None:
                has_input = bool(self.has_input_fn())
            else:
                has_input = bool(self._io.poll_key())
            self.memory[MR_KBSR] = 0x8000 if has_input else 0x0000

            if self.kbsr_poll_fn is not None:
                self.kbsr_poll_fn(has_input)

            return self.memory[MR_KBSR]

        # Registro de datos de teclado (KBDR)
        elif address == MR_KBDR:
            if self.input_fn is not None:
                ch = self.input_fn()
                self.memory[MR_KBDR] = ch & 0xFF
            else:
                ch = self._io.read_key()
                if ch is not None:
                    self.memory[MR_KBDR] = ch & 0xFF
            val = self.memory[MR_KBDR]
            self.memory[MR_KBSR] = 0x0000  # Limpiar bandera de teclado al leer datos
            if self.kbsr_poll_fn is not None:
                self.kbsr_poll_fn(True)
            return val

        elif address == MR_DSR:
            return 0x8000  # Siempre listo para imprimir

        return self.memory[address]

    def mem_write(self, address: int, val: int):
        """Escribe palabra enmascarada; step y editores comparten efectos MMIO.

        DDR emite byte bajo antes de almacenar. MCR sin reloj detiene CPU,
        restaura registros/CC del snapshot HALT y lo limpia antes de almacenar;
        no restaura PC. Si falla la emisión DDR no se almacena la palabra.
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
        """Atiende TRAP nativo o fallback de vector cero, invocado por step.

        GETC/IN consumen entrada; OUT/PUTS/PUTSP emiten; HALT para running.
        Un vector genérico no nulo cambia PC; cero emite diagnóstico por el
        puerto, separado de output_fn. Las rutinas nativas no recalculan CC.
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
            self._output_text(
                "\n*** HALT: Procesador detenido por instrucción TRAP x25 ***\n"
            )
            self.running = False

        else:
            # Trap de vector genérico: salto por tabla de vectores si estuviera cargada
            vector_addr = self.mem_read(trapvect)
            if vector_addr != 0:
                self.pc = vector_addr
            else:
                self._io.report(f"[Aviso] TRAP x{trapvect:02X} no implementado.")

    def step(self) -> bool:
        """Ejecuta fetch/decode/execute incluso con running=False y cuenta el paso.

        Invocado por run, depurador y GUI; delega memoria/MMIO y TRAP. Guarda
        R7 antes del snapshot HALT. RTI es no-op educativo; opcode reservado
        diagnostica por el puerto y detiene. Los callbacks pueden propagar errores.

        Returns:
            bool: Estado running posterior, no indicador de si hubo instrucción.
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
            self._io.report(
                f"[Error] Código de operación reservado/inválido en x{curr_pc:04X} (x{instr:04X})"
            )
            self.running = False

        self.instruction_count += 1
        return self.running

    def run(self, max_steps: Optional[int] = None) -> int:
        """Ejecuta desde PC actual hasta parada o límite acumulado de instrucciones.

        CLI/tests lo invocan; activa running y delega cada ciclo a step.
        max_steps=None o 0 no limita; alcanzar límite conserva running y CPU.
        Ctrl+C emite diagnóstico por el puerto y desactiva running.

        Returns:
            int: Contador acumulado, no sólo pasos de esta llamada.
        """
        self.running = True
        try:
            while self.running:
                if max_steps and self.instruction_count >= max_steps:
                    self._io.report(
                        f"\n[Aviso] Se alcanzó el límite máximo de pasos ({max_steps})."
                    )
                    break
                self.step()
        except KeyboardInterrupt:
            self._io.report(
                "\n[Interrupción] Ejecución pausada por el usuario (Ctrl+C)."
            )
            self.running = False
        return self.instruction_count
