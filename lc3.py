#!/usr/bin/env python3
"""Lanzador de línea de comandos raíz para la arquitectura LC-3.

Responsabilidad:
    Servir como punto de entrada ejecutable principal desde la raíz del repositorio, delegando
    directamente el flujo y argumentos hacia el enrutador CLI del paquete (`lc3.cli.main`).
"""
import sys
from lc3.cli import main

if __name__ == "__main__":
    sys.exit(main())
