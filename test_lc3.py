"""Entrada unittest conservada; descubre tests sin reexportar ni duplicar clases."""

import unittest
from pathlib import Path
from typing import Optional


def load_tests(
    loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: Optional[str]
) -> unittest.TestSuite:
    """Devuelve al loader la suite tests/ desde raíz absoluta, no desde el cwd.

    unittest invoca este hook desde ejecución directa, -m o cmd_test. tests es
    la suite previa del loader; se sustituye por descubrimiento sin reexports.
    """
    root = Path(__file__).resolve().parent
    return loader.discover(
        str(root / "tests"), pattern=pattern or "test_*.py", top_level_dir=str(root)
    )


if __name__ == "__main__":
    unittest.main()
