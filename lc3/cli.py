"""
lc3/cli.py - Interfaz de línea de comandos (CLI) principal para la arquitectura LC-3.
Permite ensamblar código fuente .asm, ejecutar binarios .obj, depurar interactivamente
y correr la suite de pruebas.
"""

import sys
import os
import argparse
from .assembler import assemble_file, AssemblyError
from .sim import LC3Simulator
from .debugger import LC3Debugger


def cmd_asm(args):
    """Subcomando para ensamblar código fuente LC-3."""
    src = args.source
    if not os.path.isfile(src):
        print(f"Error: El archivo fuente '{src}' no existe.", file=sys.stderr)
        return 1

    obj = args.output
    hex_path = args.hex_file
    if args.hex and not hex_path:
        base = os.path.splitext(obj if obj else src)[0]
        hex_path = base + ".hex"

    try:
        orig, count = assemble_file(src, obj_path=obj, hex_path=hex_path)
        base = os.path.splitext(obj if obj else src)[0]
        print(f"Ensamblado exitoso:")
        print(f"  Fuente:     {src}")
        print(f"  Binario:    {base}.obj (Origen: x{orig:04X}, Palabras: {count})")
        print(f"  Símbolos:   {base}.sym")
        if hex_path:
            print(f"  Hex dump:   {hex_path}")
        return 0
    except AssemblyError as e:
        print(f"Error de ensamblado:\n{e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error inesperado al ensamblar: {e}", file=sys.stderr)
        return 1


def cmd_run(args):
    """Subcomando para ejecutar un binario LC-3 en modo directo."""
    obj = args.object_file
    if not os.path.isfile(obj):
        # Si el usuario pasó un .asm, ensamblarlo primero automáticamente
        if obj.lower().endswith(".asm"):
            asm_obj = obj[:-4] + ".obj"
            print(f"Ensamblando automáticamente '{obj}' a '{asm_obj}'...")
            try:
                assemble_file(obj, obj_path=asm_obj)
                obj = asm_obj
            except Exception as e:
                print(f"Error al auto-ensamblar: {e}", file=sys.stderr)
                return 1
        else:
            print(f"Error: El archivo '{obj}' no existe.", file=sys.stderr)
            return 1

    sim = LC3Simulator()
    try:
        orig = sim.load_obj(obj)
    except Exception as e:
        print(f"Error al cargar archivo .obj: {e}", file=sys.stderr)
        return 1

    # Cargar tabla de símbolos si existe junto al archivo
    sym_file = os.path.splitext(obj)[0] + ".sym"
    if os.path.isfile(sym_file):
        sim.load_sym(sym_file)

    if args.verbose:
        print(f"Ejecutando '{obj}' desde origen x{orig:04X}...")

    total_steps = sim.run(max_steps=args.max_steps)

    if args.verbose or args.stats:
        print(f"\n[Estadísticas] Instrucciones ejecutadas: {total_steps}")
        print(f"[Estado Final] PC: x{sim.pc:04X}, R0: x{sim.reg[0]:04X}, R1: x{sim.reg[1]:04X}")

    return 0


def cmd_debug(args):
    """Subcomando para depurar un binario LC-3 interactivamente."""
    obj = args.object_file
    if not os.path.isfile(obj):
        if obj.lower().endswith(".asm"):
            asm_obj = obj[:-4] + ".obj"
            print(f"Ensamblando automáticamente '{obj}' para depuración...")
            try:
                assemble_file(obj, obj_path=asm_obj)
                obj = asm_obj
            except Exception as e:
                print(f"Error al auto-ensamblar: {e}", file=sys.stderr)
                return 1
        else:
            print(f"Error: El archivo '{obj}' no existe.", file=sys.stderr)
            return 1

    sim = LC3Simulator()
    try:
        orig = sim.load_obj(obj)
    except Exception as e:
        print(f"Error al cargar archivo .obj: {e}", file=sys.stderr)
        return 1

    sym_file = args.sym if args.sym else (os.path.splitext(obj)[0] + ".sym")
    if os.path.isfile(sym_file):
        sim.load_sym(sym_file)

    dbg = LC3Debugger(sim, start_pc=orig)
    dbg.interactive_loop()
    return 0


def cmd_test(args):
    """Subcomando para ejecutar la suite de pruebas unitarias."""
    import unittest
    tests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests")
    suite = unittest.defaultTestLoader.discover(tests_dir)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def cmd_gui(args):
    """Subcomando para iniciar la interfaz gráfica de usuario."""
    from .gui import LC3GUI
    app = LC3GUI(initial_file=args.file)
    app.mainloop()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Conjunto de herramientas para la arquitectura LC-3 (Ensamblador y Simulador/VM)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Ejemplos de uso:
  python lc3.py              (Inicia la interfaz gráfica de usuario)
  python lc3.py gui [prog]   (Inicia la GUI con un programa opcional)
  python lc3.py asm prog.asm (Ensambla código .asm a .obj)
  python lc3.py run prog.obj (Ejecuta en modo consola directa)
  python lc3.py debug prog   (Depurador interactivo de consola)
  python lc3.py test         (Ejecuta la suite de pruebas unitarias)
"""
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Comandos disponibles")

    # Subcomando: asm
    p_asm = subparsers.add_parser("asm", help="Ensambla código fuente .asm a binario .obj")
    p_asm.add_argument("source", help="Ruta al archivo fuente .asm")
    p_asm.add_argument("-o", "--output", help="Ruta de salida para el archivo .obj")
    p_asm.add_argument("--hex", action="store_true", help="Genera también un volcado .hex de texto")
    p_asm.add_argument("--hex-file", help="Ruta específica para el archivo .hex")
    p_asm.set_defaults(func=cmd_asm)

    # Subcomando: run
    p_run = subparsers.add_parser("run", help="Ejecuta un archivo .obj en el simulador")
    p_run.add_argument("object_file", help="Ruta al archivo binario .obj (o .asm para auto-ensamblado)")
    p_run.add_argument("--max-steps", type=int, default=None, help="Límite máximo de instrucciones a ejecutar")
    p_run.add_argument("-v", "--verbose", action="store_true", help="Muestra mensajes informativos")
    p_run.add_argument("--stats", action="store_true", help="Muestra estadísticas al finalizar")
    p_run.set_defaults(func=cmd_run)

    # Subcomando: debug
    p_dbg = subparsers.add_parser("debug", help="Inicia la consola interactiva de depuración")
    p_dbg.add_argument("object_file", help="Ruta al archivo binario .obj")
    p_dbg.add_argument("-s", "--sym", help="Ruta a la tabla de símbolos .sym")
    p_dbg.set_defaults(func=cmd_debug)

    # Subcomando: test
    p_test = subparsers.add_parser("test", help="Ejecuta la suite de pruebas unitarias")
    p_test.set_defaults(func=cmd_test)

    # Subcomando: gui
    p_gui = subparsers.add_parser("gui", help="Inicia la interfaz gráfica de usuario (GUI)")
    p_gui.add_argument("file", nargs="?", default=None, help="Archivo .asm o .obj a cargar inicialmente (opcional)")
    p_gui.set_defaults(func=cmd_gui)

    # Si no se proporcionan argumentos, lanzar la interfaz gráfica por defecto
    if len(sys.argv) == 1:
        sys.argv.append("gui")

    # Manejo de atajos directos (ej: python lc3.py archivo.asm)
    elif len(sys.argv) == 2 and sys.argv[1] not in ("-h", "--help", "asm", "run", "debug", "test", "gui"):
        arg = sys.argv[1]
        if arg.lower().endswith(".asm"):
            sys.argv.insert(1, "asm")
        elif arg.lower().endswith(".obj"):
            sys.argv.insert(1, "run")

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
