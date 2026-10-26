"""Comprueba conversiones de la ISA para el descubrimiento de pruebas unittest."""

import unittest

from lc3.domain.isa import sign_extend, to_uint16, to_int16


class TestLC3Core(unittest.TestCase):
    """Agrupa comprobaciones unittest de representación numérica pura de la ISA."""

    def test_sign_extend(self):
        """Comprueba límites positivos y negativos de extensiones de 5 y 9 bits."""
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
        """Comprueba wrap unsigned y límites signed de las conversiones de 16 bits."""
        self.assertEqual(to_uint16(-1), 0xFFFF)
        self.assertEqual(to_uint16(65536), 0)
        self.assertEqual(to_int16(0xFFFF), -1)
        self.assertEqual(to_int16(0x7FFF), 32767)
        self.assertEqual(to_int16(0x8000), -32768)
