"""Depurador interactivo de consola para la arquitectura LC-3.

Responsabilidad:
    Proveer una interfaz de depuración interactiva estilo GDB por consola, permitiendo ejecución
    paso a paso (step), salto de subrutinas y TRAPs (step over), gestión de breakpoints por
    dirección o etiqueta, e inspección o edición dinámica de registros y celdas de memoria.
"""

from typing import Optional, Set
from .core import (
    MASK_16, to_uint16, to_int16, get_cc_name, disassemble_instruction,
    OP_JSR, OP_TRAP, TRAP_HALT
)
from .sim import LC3Simulator


class LC3Debugger:
    """Controlador de depuración interactiva de consola para la máquina virtual LC-3.

    Attributes:
        sim (LC3Simulator): Instancia del simulador emulado bajo control.
        orig_pc (int): Dirección base de inicio de ejecución (habitualmente x3000).
        breakpoints (Set[int]): Conjunto de direcciones de memoria con puntos de interrupción activos.
        last_cmd (str): Último comando de consola ingresado para permitir repetición con [Enter].
    """

    def __init__(self, sim: LC3Simulator, start_pc: int = 0x3000):
        self.sim = sim
        self.orig_pc = start_pc
        self.breakpoints: Set[int] = set()
        self.last_cmd = ""

    def parse_address_or_symbol(self, token: str) -> Optional[int]:
        """Resuelve una dirección de memoria a partir de una etiqueta simbólica o literal numérico.

        Acepta nombres de etiquetas cargadas en la tabla de símbolos del simulador,
        así como formatos hexadecimales ('x3000', '0x3000', '3000') y decimales ('#12288').

        Args:
            token (str): Cadena ingresada por el usuario en la consola de depuración.

        Returns:
            Optional[int]: Dirección de 16 bits sin signo [0x0000, 0xFFFF] o None si no es válida.
        """
        # Buscar en la tabla invertida de símbolos
        for addr, name in self.sim.symbols.items():
            if name.lower() == token.lower():
                return addr

        token_upper = token.upper()
        try:
            if token_upper.startswith("0X"):
                return int(token[2:], 16) & MASK_16
            elif token_upper.startswith("X"):
                return int(token[1:], 16) & MASK_16
            elif token_upper.startswith("#"):
                return int(token[1:], 10) & MASK_16
            else:
                # Intento en hex si tiene letras hex, o dec si es puro dígito
                return int(token, 16) & MASK_16
        except ValueError:
            return None

    def print_registers(self):
        """Muestra en consola el estado actual de los registros R0–R7, PC, CC y la instrucción en curso."""
        print("\n" + "=" * 62)
        print("  ESTADO DE REGISTROS LC-3")
        print("=" * 62)
        r = self.sim.reg
        for i in range(0, 8, 2):
            val1 = r[i]
            val2 = r[i+1]
            s1 = to_int16(val1)
            s2 = to_int16(val2)
            print(f"  R{i}: x{val1:04X} ({s1:>6})          R{i+1}: x{val2:04X} ({s2:>6})")

        cc_str = get_cc_name(self.sim.cond)
        print("-" * 62)
        pc_sym = f" ({self.sim.symbols[self.sim.pc]})" if self.sim.pc in self.sim.symbols else ""
        print(f"  PC : x{self.sim.pc:04X}{pc_sym:<16} CC: [{cc_str}]  Instrucciones: {self.sim.instruction_count}")
        
        # Mostrar siguiente instrucción a ejecutar
        curr_instr = self.sim.mem_read(self.sim.pc)
        dis = disassemble_instruction(curr_instr, self.sim.pc, self.sim.symbols)
        print(f"  -> x{self.sim.pc:04X}: x{curr_instr:04X}  {dis}")
        print("=" * 62 + "\n")

    def print_memory(self, start_addr: int, count: int = 8):
        """Vuelca en consola una región contigua de memoria formateada en hex, decimal y ASCII.

        Args:
            start_addr (int): Dirección inicial de volcado.
            count (int, optional): Cantidad de palabras consecutivas a mostrar. Por defecto 8.
        """
        print(f"\n--- Memoria desde x{start_addr:04X} ({count} palabras) ---")
        for i in range(count):
            addr = (start_addr + i) & MASK_16
            val = self.sim.mem_read(addr)
            sym = f"<{self.sim.symbols[addr]}>" if addr in self.sim.symbols else ""
            char = chr(val & 0xFF) if 32 <= (val & 0xFF) <= 126 else "."
            print(f"  x{addr:04X}: x{val:04X} ({to_int16(val):>6})  '{char}'  {sym}")
        print()

    def disassemble(self, start_addr: int, count: int = 10):
        """Desensambla e imprime un bloque de instrucciones a partir de una dirección dada.

        Resalta visualmente si la dirección coincide con el PC actual o si posee un breakpoint activo.

        Args:
            start_addr (int): Dirección inicial de desensamblado.
            count (int, optional): Número de instrucciones a desensamblar. Por defecto 10.
        """
        for i in range(count):
            addr = (start_addr + i) & MASK_16
            val = self.sim.mem_read(addr)
            dis = disassemble_instruction(val, addr, self.sim.symbols)
            marker = "-->" if addr == self.sim.pc else "   "
            bp_marker = "[*]" if addr in self.breakpoints else "   "
            sym = f" {self.sim.symbols[addr]}:" if addr in self.sim.symbols else ""
            print(f"{marker} {bp_marker} x{addr:04X}: x{val:04X}  {dis:<24}{sym}")
        print()

    def run_until_break_or_halt(self):
        """Ejecuta instrucciones continuamente hasta alcanzar un breakpoint, HALT o interrupción manual."""
        self.sim.running = True
        try:
            while self.sim.running:
                # Comprobar si el PC actual está en los breakpoints (excepto si acabamos de resumir)
                if self.sim.pc in self.breakpoints:
                    print(f"\n[Breakpoint alcanzado en x{self.sim.pc:04X}]")
                    break

                self.sim.step()

                if self.sim.pc in self.breakpoints and self.sim.running:
                    print(f"\n[Breakpoint alcanzado en x{self.sim.pc:04X}]")
                    break
        except KeyboardInterrupt:
            print("\n[Pausa] Ejecución interrumpida con Ctrl+C.")
            self.sim.running = False

    def step_over(self):
        """Avanza una instrucción omitiendo la introspección interna en subrutinas o TRAPs (Step Over)."""
        instr = self.sim.mem_read(self.sim.pc)
        op = (instr >> 12) & 0xF
        trapvect = instr & 0xFF

        is_subroutine = (op == OP_JSR) or (op == OP_TRAP and trapvect != TRAP_HALT)

        if is_subroutine:
            ret_addr = (self.sim.pc + 1) & MASK_16
            temp_bp = ret_addr not in self.breakpoints
            if temp_bp:
                self.breakpoints.add(ret_addr)

            self.sim.running = True
            try:
                # Ejecutar al menos un paso para entrar a la subrutina
                self.sim.step()
                while self.sim.running and self.sim.pc != ret_addr:
                    if self.sim.pc in self.breakpoints:
                        print(f"\n[Breakpoint alcanzado en x{self.sim.pc:04X}]")
                        break
                    self.sim.step()
            finally:
                if temp_bp:
                    self.breakpoints.discard(ret_addr)
        else:
            self.sim.step()

    def print_help(self):
        print("""
Comandos del Depurador LC-3:
  s, step               Ejecuta una sola instrucción (entra en subrutinas).
  n, next               Ejecuta la siguiente instrucción saltando subrutinas (Step Over).
  c, continue           Continúa la ejecución hasta un breakpoint o HALT.
  b, break <addr|label> Establece un punto de interrupción (ej: b x3005 o b LOOP).
  del <addr|label>      Elimina un punto de interrupción existente.
  info b                Muestra todos los puntos de interrupción activos.
  r, reg                Muestra los registros R0-R7, PC, CC y la instrucción actual.
  m, mem <addr> [n]     Muestra 'n' palabras de memoria (ej: m x3000 8).
  d, disasm [addr] [n]  Desensambla 'n' instrucciones desde la dirección o PC.
  set r<0-7> <val>      Modifica el valor de un registro (ej: set r0 #42 o set r1 xFF).
  set mem <addr> <val>  Modifica el valor en una dirección de memoria.
  set pc <addr>         Modifica el contador de programa (PC).
  k, key <char|code>    Inyecta una tecla al registro de teclado para GETC/IN (ej: key a).
  reset                 Reinicia los registros y el PC a la dirección de origen.
  h, help               Muestra este menú de ayuda.
  q, quit, exit         Sale del depurador.
  [Enter vacío]         Repite el último comando ejecutado (útil para step continuo).
""")

    def interactive_loop(self):
        """Inicia el bucle REPL interactivo de comandos de depuración en consola."""
        print("=" * 62)
        print("  DEPURADOR INTERACTIVO LC-3")
        print("  Escribe 'help' para ver los comandos disponibles.")
        print("=" * 62)

        self.print_registers()

        while True:
            try:
                prompt = f"(lc3-dbg x{self.sim.pc:04X}) "
                line = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nSaliendo del depurador.")
                break

            if not line:
                line = self.last_cmd
            else:
                self.last_cmd = line

            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("q", "quit", "exit"):
                print("Fin de la sesión de depuración.")
                break

            elif cmd in ("h", "help", "?"):
                self.print_help()

            elif cmd in ("s", "step"):
                self.sim.step()
                self.print_registers()

            elif cmd in ("n", "next"):
                self.step_over()
                self.print_registers()

            elif cmd in ("c", "continue"):
                self.run_until_break_or_halt()
                self.print_registers()

            elif cmd in ("b", "break"):
                if not args:
                    print("Uso: break <dirección o etiqueta> (ej: break x3005 o break LOOP)")
                    continue
                addr = self.parse_address_or_symbol(args[0])
                if addr is None:
                    print(f"Dirección o etiqueta inválida: '{args[0]}'")
                else:
                    self.breakpoints.add(addr)
                    sym_info = f" ({self.sim.symbols[addr]})" if addr in self.sim.symbols else ""
                    print(f"Breakpoint añadido en x{addr:04X}{sym_info}.")

            elif cmd in ("del", "delete"):
                if not args:
                    print("Uso: delete <dirección o etiqueta>")
                    continue
                addr = self.parse_address_or_symbol(args[0])
                if addr in self.breakpoints:
                    self.breakpoints.remove(addr)
                    print(f"Breakpoint eliminado en x{addr:04X}.")
                else:
                    print(f"No hay breakpoint en esa dirección.")

            elif cmd == "info" and args and args[0].lower() in ("b", "breakpoints"):
                if not self.breakpoints:
                    print("No hay puntos de interrupción activos.")
                else:
                    print("Puntos de interrupción activos:")
                    for bp in sorted(self.breakpoints):
                        sym_info = f" ({self.sim.symbols[bp]})" if bp in self.sim.symbols else ""
                        print(f"  - x{bp:04X}{sym_info}")

            elif cmd in ("r", "reg", "registers"):
                self.print_registers()

            elif cmd in ("m", "mem", "memory"):
                start = self.sim.pc
                count = 8
                if len(args) >= 1:
                    addr = self.parse_address_or_symbol(args[0])
                    if addr is not None:
                        start = addr
                if len(args) >= 2:
                    try:
                        count = int(args[1])
                    except ValueError:
                        pass
                self.print_memory(start, count)

            elif cmd in ("d", "dis", "disasm"):
                start = self.sim.pc
                count = 10
                if len(args) >= 1:
                    addr = self.parse_address_or_symbol(args[0])
                    if addr is not None:
                        start = addr
                if len(args) >= 2:
                    try:
                        count = int(args[1])
                    except ValueError:
                        pass
                self.disassemble(start, count)

            elif cmd == "set":
                if len(args) < 2:
                    print("Uso: set r<0-7> <val>  O  set mem <addr> <val>  O  set pc <addr>")
                    continue
                sub = args[0].lower()
                if sub.startswith("r") and len(sub) == 2 and sub[1].isdigit():
                    r_idx = int(sub[1])
                    if 0 <= r_idx <= 7:
                        val = self.parse_address_or_symbol(args[1])
                        if val is not None:
                            self.sim.reg[r_idx] = to_uint16(val)
                            self.sim.update_flags(r_idx)
                            print(f"R{r_idx} = x{self.sim.reg[r_idx]:04X} ({to_int16(self.sim.reg[r_idx])})")
                    else:
                        print("Registro inválido (R0 a R7).")
                elif sub == "mem":
                    if len(args) < 3:
                        print("Uso: set mem <dirección> <valor>")
                        continue
                    addr = self.parse_address_or_symbol(args[1])
                    val = self.parse_address_or_symbol(args[2])
                    if addr is not None and val is not None:
                        self.sim.mem_write(addr, val)
                        print(f"mem[x{addr:04X}] = x{val:04X}")
                elif sub == "pc":
                    val = self.parse_address_or_symbol(args[1])
                    if val is not None:
                        self.sim.pc = val & MASK_16
                        print(f"PC = x{self.sim.pc:04X}")
                else:
                    print("Opción de set desconocida. Usa 'set r0 <val>', 'set mem <addr> <val>' o 'set pc <addr>'.")

            elif cmd == "reset":
                self.sim.reset(self.orig_pc)
                print(f"Procesador reiniciado. PC = x{self.orig_pc:04X}.")
                self.print_registers()

            elif cmd in ("k", "key"):
                if not args:
                    print("Uso: key <carácter o código> (ej: key a o key 65)")
                    continue
                arg = args[0]
                ch = ord(arg) if len(arg) == 1 else (int(arg) & 0xFF if arg.isdigit() else ord(arg[0]))
                if not hasattr(self.sim, "_cli_dbg_buf"):
                    self.sim._cli_dbg_buf = []
                    self.sim.has_input_fn = lambda: len(self.sim._cli_dbg_buf) > 0
                    self.sim.input_fn = lambda: self.sim._cli_dbg_buf.pop(0) if self.sim._cli_dbg_buf else 0
                self.sim._cli_dbg_buf.append(ch)
                print(f"[Teclado] Carácter '{chr(ch)}' (ASCII {ch}) cargado al búfer de teclado.")

            else:
                # Si el procesador está sondeando el teclado en el SO (GETC / IN) y se ingresa un solo carácter:
                curr_pc = self.sim.pc
                is_polling_keyboard = curr_pc in (0x0200, 0x0201, 0x0228, 0x0229)
                if is_polling_keyboard and len(cmd) == 1:
                    ch = ord(cmd)
                    if not hasattr(self.sim, "_cli_dbg_buf"):
                        self.sim._cli_dbg_buf = []
                        self.sim.has_input_fn = lambda: len(self.sim._cli_dbg_buf) > 0
                        self.sim.input_fn = lambda: self.sim._cli_dbg_buf.pop(0) if self.sim._cli_dbg_buf else 0
                    self.sim._cli_dbg_buf.append(ch)
                    print(f"[Teclado] Carácter '{cmd}' (ASCII {ch}) inyectado. Avanzando sondeo...")
                    while self.sim.running and self.sim.pc in (0x0200, 0x0201, 0x0228, 0x0229):
                        self.sim.step()
                    self.print_registers()
                else:
                    print(f"Comando desconocido: '{cmd}'. Escribe 'help' para ver la lista de comandos.")
