"""Comprueba CPU, memoria y SO con máquinas reales creadas para unittest."""

import unittest

from lc3.bootstrap import create_simulator, EXAMPLES_DIR
from lc3.domain.assembler import LC3Assembler
from lc3.domain.isa import FL_ZRO, MR_MCR, to_int16
from lc3.domain.machine import LC3Simulator
from lc3.infrastructure.program_files import load_obj


class TestLC3Simulator(unittest.TestCase):
    """Ejercita CPU real, memoria y servicios del SO desde unittest."""

    def setUp(self):
        """Crea una máquina con imagen SO real aislada para cada escenario."""
        self.sim = create_simulator()

    def run_assembly(self, source_code: str) -> LC3Simulator:
        """Ensambla para tests, carga memoria/símbolos propios y ejecuta hasta HALT.

        Devuelve self.sim mutado; propaga errores de ensamblado y ejecución.
        """
        asm = LC3Assembler()
        orig, words, symbols = asm.assemble(source_code)
        for i, w in enumerate(words):
            self.sim.memory[orig + i] = w
        self.sim.symbols = {v: k for k, v in symbols.items()}
        self.sim.pc = orig
        self.sim.run()
        return self.sim

    def test_arithmetic_execution(self):
        """Comprueba resultados aritméticos y CC de usuario tras HALT del SO."""
        code = """
        .ORIG x3000
        AND R0, R0, #0
        ADD R0, R0, #5
        ADD R1, R0, #-10
        ADD R2, R0, #-5
        HALT
        .END
        """
        self.run_assembly(code)
        self.assertEqual(self.sim.reg[0], 5)
        self.assertEqual(to_int16(self.sim.reg[1]), -5)
        self.assertEqual(self.sim.reg[2], 0)
        self.assertEqual(self.sim.cond, FL_ZRO)

    def test_branch_and_subroutine(self):
        """Comprueba JSR/RET y la mutación de R1 al duplicar mediante subrutina."""
        code = """
        .ORIG x3000
        AND R1, R1, #0
        ADD R1, R1, #3
        JSR DOUBLE_R1
        HALT

DOUBLE_R1
        ADD R1, R1, R1
        RET
        .END
        """
        self.run_assembly(code)
        self.assertEqual(self.sim.reg[1], 6)

    def test_memory_load_store(self):
        """Comprueba LD/ADD/ST y persistencia del dato de usuario tras HALT."""
        code = """
        .ORIG x3000
        LD  R1, VALUE
        ADD R1, R1, #1
        ST  R1, VALUE
        HALT
VALUE   .FILL #100
        .END
        """
        self.run_assembly(code)
        addr = 0x3004
        self.assertEqual(self.sim.memory[addr], 101)

    def test_os_vector_table_and_routines(self):
        """Verifica que la tabla de vectores TRAP y el código del SO se carguen en memoria."""
        sim = create_simulator()
        self.assertEqual(sim.memory[0x0020], 0x0200)  # GETC
        self.assertEqual(sim.memory[0x0021], 0x0206)  # OUT
        self.assertEqual(sim.memory[0x0022], 0x020F)  # PUTS
        self.assertEqual(sim.memory[0x0023], 0x0223)  # IN
        self.assertEqual(sim.memory[0x0024], 0x0246)  # PUTSP
        self.assertEqual(sim.memory[0x0025], 0x0273)  # HALT

    def test_os_getc_polling_step_by_step(self):
        """Verifica la ejecución del sondeo en GETC del SO paso a paso."""
        code = """
        .ORIG x3000
        GETC
        HALT
        .END
        """
        asm = LC3Assembler()
        orig, words, symbols = asm.assemble(code)
        sim = create_simulator()
        for i, w in enumerate(words):
            sim.memory[orig + i] = w
        sim.pc = orig
        sim.running = True

        # Paso 1: Salto a manejador GETC en x0200
        sim.step()
        self.assertEqual(sim.pc, 0x0200)
        self.assertEqual(sim.reg[7], 0x3001)  # Retorno a usuario

        # Paso 2: LDI R0, KBSR (sin tecla, retorna 0)
        sim.step()
        self.assertEqual(sim.pc, 0x0201)
        self.assertEqual(sim.reg[0], 0x0000)

        # Paso 3: BRzp x0200 (se toma el salto de sondeo)
        sim.step()
        self.assertEqual(sim.pc, 0x0200)

        # Ahora el usuario presiona una tecla 'Z' (ASCII 90)
        input_buf = [ord("Z")]
        sim.input_fn = lambda: input_buf.pop(0)
        sim.has_input_fn = lambda: len(input_buf) > 0

        # Paso 4: LDI R0, KBSR (tecla lista -> bit 15 = 1, x8000)
        sim.step()
        self.assertEqual(sim.pc, 0x0201)
        self.assertEqual(sim.reg[0], 0x8000)

        # Paso 5: BRzp x0200 (no se toma el salto porque R0 es negativo)
        sim.step()
        self.assertEqual(sim.pc, 0x0202)

        # Paso 6: LDI R0, KBDR (lee el carácter 90 'Z')
        sim.step()
        self.assertEqual(sim.pc, 0x0203)
        self.assertEqual(sim.reg[0], ord("Z"))

        # Paso 7: RET (retorna a x3001 en el código de usuario)
        sim.step()
        self.assertEqual(sim.pc, 0x3001)
        self.assertEqual(sim.reg[0], ord("Z"))

    def test_os_in_and_echo_execution(self):
        """Verifica la ejecución de TRAP IN (x23) con eco en pantalla y retorno."""
        code = """
        .ORIG x3000
        IN
        HALT
        .END
        """
        asm = LC3Assembler()
        orig, words, symbols = asm.assemble(code)
        sim = create_simulator()
        for i, w in enumerate(words):
            sim.memory[orig + i] = w
        sim.pc = orig

        input_buf = [ord("M")]
        sim.input_fn = lambda: input_buf.pop(0)
        sim.has_input_fn = lambda: len(input_buf) > 0

        output_chars = []
        sim.output_fn = lambda ch: output_chars.append(ch)

        sim.run()
        out_str = "".join(output_chars)
        self.assertIn("Input a character: ", out_str)
        self.assertIn("M", out_str)
        self.assertEqual(sim.reg[0], ord("M"))

    def test_reset_restores_os_and_preserves_user_memory(self):
        """Comprueba que reset restaure el SO sin borrar RESULT ni símbolos de usuario.

        Ejecuta mult con la composición real y altera memoria y símbolos públicos
        del SO para detectar alias con las plantillas privadas de la máquina.
        """
        sim = self.sim
        os_word = sim.memory[0x0200]
        os_symbols = sim.os_symbols.copy()
        load_obj(sim, str(EXAMPLES_DIR / "mult.obj"))
        sim.run()
        self.assertEqual(sim.memory[0x300E], 42)

        sim.memory[0x0200] = os_word ^ 0xFFFF
        sim.os_symbols[0x0200] = "SIMBOLO_OS_ALTERADO"
        sim.symbols[0x0200] = "ETIQUETA_USUARIO"
        sim.reset(0x3000)

        self.assertEqual(sim.memory[0x300E], 42)
        self.assertEqual(sim.memory[0x0200], os_word)
        self.assertEqual(sim.os_symbols, os_symbols)
        self.assertEqual(sim.reg, [0] * 8)
        self.assertEqual(sim.instruction_count, 0)
        self.assertFalse(sim.running)
        self.assertEqual(sim.memory[MR_MCR], 0x8000)
        self.assertEqual(sim.symbols[0x0200], "ETIQUETA_USUARIO")
