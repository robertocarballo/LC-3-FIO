"""
test_lc3.py - Suite de pruebas unitarias y de integración para la arquitectura LC-3.
Verifica ensamblador, instrucciones de máquina, registros, flags y simulación completa.
"""

import unittest
import io
import sys
import os

# Asegurar que el paquete lc3 sea importable directamente al correr este archivo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lc3.core import (
    MASK_16, FL_POS, FL_ZRO, FL_NEG,
    sign_extend, to_uint16, to_int16, disassemble_instruction
)
from lc3.assembler import LC3Assembler, AssemblyError, assemble_file
from lc3.sim import LC3Simulator
from lc3.debugger import LC3Debugger

class TestLC3Core(unittest.TestCase):
    def test_sign_extend(self):
        # 5 bits: rango [-16, 15]
        self.assertEqual(sign_extend(0b01111, 5), 15)
        self.assertEqual(sign_extend(0b10000, 5), -16)
        self.assertEqual(sign_extend(0b11111, 5), -1)
        self.assertEqual(sign_extend(0b00000, 5), 0)

        # 9 bits: rango [-256, 255]
        self.assertEqual(sign_extend(0b011111111, 9), 255)
        self.assertEqual(sign_extend(0b100000000, 9), -256)
        self.assertEqual(sign_extend(0b111111111, 9), -1)

    def test_conversions(self):
        self.assertEqual(to_uint16(-1), 0xFFFF)
        self.assertEqual(to_uint16(65536), 0)
        self.assertEqual(to_int16(0xFFFF), -1)
        self.assertEqual(to_int16(0x7FFF), 32767)
        self.assertEqual(to_int16(0x8000), -32768)


class TestLC3Assembler(unittest.TestCase):
    def setUp(self):
        self.assembler = LC3Assembler()

    def test_encode_add_and_not(self):
        code = """
        .ORIG x3000
        ADD R1, R2, R3
        ADD R4, R5, #7
        ADD R6, R7, #-5
        AND R0, R1, R2
        AND R3, R4, #0
        NOT R5, R6
        .END
        """
        orig, words, symbols = self.assembler.assemble(code)
        self.assertEqual(orig, 0x3000)
        # ADD R1, R2, R3: 0001 001 010 0 00 011 = 0x1283
        self.assertEqual(words[0], 0x1283)
        # ADD R4, R5, #7: 0001 100 101 1 00111 = 0x1967
        self.assertEqual(words[1], 0x1967)
        # ADD R6, R7, #-5: 0001 110 111 1 11011 = 0x1DFB
        self.assertEqual(words[2], 0x1DFB)
        # AND R0, R1, R2: 0101 000 001 0 00 010 = 0x5042
        self.assertEqual(words[3], 0x5042)
        # AND R3, R4, #0: 0101 011 100 1 00000 = 0x5720
        self.assertEqual(words[4], 0x5720)
        # NOT R5, R6:     1001 101 110 111111  = 0x9BBF
        self.assertEqual(words[5], 0x9BBF)

    def test_encode_branches_and_labels(self):
        code = """
        .ORIG x3000
        START   BRnzp FORWARD
                BRz   START
                BRn   START
                BRp   START
        FORWARD HALT
        .END
        """
        orig, words, symbols = self.assembler.assemble(code)
        self.assertEqual(symbols["START"], 0x3000)
        self.assertEqual(symbols["FORWARD"], 0x3004)
        # START: BRnzp FORWARD (target = 0x3004, pc+1 = 0x3001, offset = +3)
        # 0000 111 000000011 = 0x0E03
        self.assertEqual(words[0], 0x0E03)
        # BRz START (target = 0x3000, pc+1 = 0x3002, offset = -2 -> 9-bit: 0x1FE)
        # 0000 010 111111110 = 0x05FE
        self.assertEqual(words[1], 0x05FE)
        # HALT: TRAP x25 -> 0xF025
        self.assertEqual(words[4], 0xF025)

    def test_encode_memory_instructions(self):
        code = """
        .ORIG x3000
        LD  R1, DATA
        ST  R1, DATA
        LDI R2, DATA
        STI R2, DATA
        LEA R3, DATA
        LDR R4, R5, #10
        STR R6, R7, #-4
        DATA .FILL #42
        .END
        """
        orig, words, symbols = self.assembler.assemble(code)
        self.assertEqual(symbols["DATA"], 0x3007)
        # DATA value
        self.assertEqual(words[7], 42)
        # LDR R4, R5, #10: 0110 100 101 001010 = 0x694A
        self.assertEqual(words[5], 0x694A)
        # STR R6, R7, #-4: 0111 110 111 111100 = 0x7DFC
        self.assertEqual(words[6], 0x7DFC)

    def test_assembler_errors(self):
        # Falta .ORIG
        with self.assertRaises(AssemblyError):
            self.assembler.assemble("ADD R1, R2, R3\n.END")

        # Inmediato imm5 fuera de rango (> 15)
        bad_imm = ".ORIG x3000\nADD R1, R2, #25\n.END"
        with self.assertRaises(AssemblyError):
            self.assembler.assemble(bad_imm)

        # Etiqueta indefinida
        bad_label = ".ORIG x3000\nBR NZP NO_EXISTE\n.END"
        with self.assertRaises(AssemblyError):
            self.assembler.assemble(bad_label)


class TestLC3Simulator(unittest.TestCase):
    def setUp(self):
        self.sim = LC3Simulator()

    def run_assembly(self, source_code: str) -> LC3Simulator:
        asm = LC3Assembler()
        orig, words, symbols = asm.assemble(source_code)
        for i, w in enumerate(words):
            self.sim.memory[orig + i] = w
        self.sim.symbols = {v: k for k, v in symbols.items()}
        self.sim.pc = orig
        self.sim.run()
        return self.sim

    def test_arithmetic_execution(self):
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

    def test_full_multiplication_program(self):
        asm_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "mult.asm")
        obj_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "mult.obj")
        orig, count = assemble_file(asm_path, obj_path=obj_path)

        sim = LC3Simulator()
        sim.load_obj(obj_path)
        sym_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "mult.sym")
        sim.load_sym(sym_path)

        # Capturar salida de texto
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            sim.run()
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        # Verificar que el resultado sea 6 * 7 = 42
        # Buscar dirección de RESULT en símbolos
        result_addr = None
        for addr, name in sim.symbols.items():
            if name == "RESULT":
                result_addr = addr
                break

        self.assertIsNotNone(result_addr)
        self.assertEqual(sim.memory[result_addr], 42)
        self.assertIn("Multiplicacion completada", output)

    def test_full_hello_program(self):
        asm_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "hello.asm")
        obj_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "hello.obj")
        assemble_file(asm_path, obj_path=obj_path)

        sim = LC3Simulator()
        sim.load_obj(obj_path)

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            sim.run()
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertIn("Hello, World!", output)

    def test_os_vector_table_and_routines(self):
        """Verifica que la tabla de vectores TRAP y el código del SO se carguen en memoria."""
        sim = LC3Simulator()
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
        sim = LC3Simulator()
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
        input_buf = [ord('Z')]
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
        self.assertEqual(sim.reg[0], ord('Z'))

        # Paso 7: RET (retorna a x3001 en el código de usuario)
        sim.step()
        self.assertEqual(sim.pc, 0x3001)
        self.assertEqual(sim.reg[0], ord('Z'))

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
        sim = LC3Simulator()
        for i, w in enumerate(words):
            sim.memory[orig + i] = w
        sim.pc = orig

        input_buf = [ord('M')]
        sim.input_fn = lambda: input_buf.pop(0)
        sim.has_input_fn = lambda: len(input_buf) > 0

        output_chars = []
        sim.output_fn = lambda ch: output_chars.append(ch)

        sim.run()
        out_str = "".join(output_chars)
        self.assertIn("Input a character: ", out_str)
        self.assertIn("M", out_str)
        self.assertEqual(sim.reg[0], ord('M'))

    def test_debugger_keyboard_injection(self):
        """Verifica que el depurador CLI pueda inyectar teclas durante el sondeo de GETC."""
        code = """
        .ORIG x3000
        GETC
        HALT
        .END
        """
        asm = LC3Assembler()
        orig, words, symbols = asm.assemble(code)
        sim = LC3Simulator()
        for i, w in enumerate(words):
            sim.memory[orig + i] = w
        dbg = LC3Debugger(sim, orig)

        # Avanzar hasta x0201 (BRzp GETC_HANDLER)
        dbg.sim.step()  # Salto a x0200
        dbg.sim.step()  # LDI R0, KBSR (0) -> PC en x0201
        self.assertEqual(dbg.sim.pc, 0x0201)

        # Inyectar 'K'
        dbg.sim._cli_dbg_buf = [ord('K')]
        dbg.sim.has_input_fn = lambda: len(dbg.sim._cli_dbg_buf) > 0
        dbg.sim.input_fn = lambda: dbg.sim._cli_dbg_buf.pop(0)

        # Paso: BRzp evalúa CC=Z (salta a x0200)
        dbg.sim.step()
        self.assertEqual(dbg.sim.pc, 0x0200)

        # Paso: LDI R0, KBSR lee 0x8000 -> CC=N
        dbg.sim.step()
        self.assertEqual(dbg.sim.pc, 0x0201)
        self.assertEqual(dbg.sim.reg[0], 0x8000)

        # Paso: BRzp evalúa CC=N -> NO salta, avanza a x0202
        dbg.sim.step()
        self.assertEqual(dbg.sim.pc, 0x0202)

        # Paso: LDI R0, KBDR lee 'K'
        dbg.sim.step()
        self.assertEqual(dbg.sim.reg[0], ord('K'))

        # Paso: RET retorna a x3001
        dbg.sim.step()
        self.assertEqual(dbg.sim.pc, 0x3001)


if __name__ == "__main__":
    unittest.main()
