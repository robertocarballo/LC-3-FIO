"""Ejecuta ejemplos completos con archivos temporales y la composición real de LC-3."""

import io
import os
import sys
import tempfile
import unittest

from lc3.bootstrap import create_simulator, EXAMPLES_DIR
from lc3.infrastructure.program_files import assemble_file, load_obj, load_sym


class TestLC3Programs(unittest.TestCase):
    """Integra fuentes de ejemplo, adaptadores de archivos y máquina mediante unittest."""

    def test_full_multiplication_program(self):
        """Ensambla mult en temporal y comprueba RESULT=42 y mensaje capturado."""
        asm_path = str(EXAMPLES_DIR / "mult.asm")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        obj_path = os.path.join(temporary.name, "mult.obj")
        sym_path = os.path.join(temporary.name, "mult.sym")
        orig, count = assemble_file(asm_path, obj_path=obj_path, sym_path=sym_path)

        sim = create_simulator()
        load_obj(sim, obj_path)
        load_sym(sim, sym_path)

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
        """Ensambla hello en temporal y comprueba su salida mediante stdout redirigido."""
        asm_path = str(EXAMPLES_DIR / "hello.asm")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        obj_path = os.path.join(temporary.name, "hello.obj")
        sym_path = os.path.join(temporary.name, "hello.sym")
        assemble_file(asm_path, obj_path=obj_path, sym_path=sym_path)

        sim = create_simulator()
        load_obj(sim, obj_path)

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            sim.run()
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertIn("Hello, World!", output)
