"""Comprueba codificación y errores del ensamblador puro mediante unittest."""

import unittest

from lc3.domain.assembler import LC3Assembler, AssemblyError


class TestLC3Assembler(unittest.TestCase):
    """Agrupa contratos de codificación y errores observables del ensamblador."""

    def setUp(self):
        """Entrega a cada test un ensamblador independiente con símbolos propios."""
        self.assembler = LC3Assembler()

    def test_encode_add_and_not(self):
        """Comprueba palabras ADD/AND/NOT con registros e inmediatos de ambos signos."""
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
        """Comprueba etiquetas PC-relativas y palabras BR/HALT emitidas."""
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
        """Comprueba ubicación de datos y codificación de memoria base/desplazamiento."""
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
        """Exige AssemblyError ante ORIG ausente, imm5 inválido y símbolo indefinido."""
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
