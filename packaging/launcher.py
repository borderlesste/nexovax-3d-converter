"""Punto de entrada de los ejecutables congelados (PyInstaller)."""
import multiprocessing
import os
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()          # imprescindible: los motores corren en procesos hijos
    # Alguna biblioteca podría intentar ejecutar "sys.executable script.py" o "-m módulo" creyendo
    # que es un intérprete de Python: en la app congelada eso abriría otra instancia. Se ignora.
    if len(sys.argv) > 1 and (sys.argv[1].endswith(".py") or sys.argv[1] in ("-m", "-c")):
        sys.exit(1)
    # Ejecutable de consola (nexovax3d-cli.exe): sin argumentos muestra la ayuda en lugar de abrir la GUI
    exe = os.path.basename(sys.executable).lower()
    if exe.startswith("nexovax3d-cli") and (len(sys.argv) == 1 or sys.argv[1] not in ("convert", "matrix", "info")):
        from u3dc.cli import main as cli_main
        sys.exit(cli_main(sys.argv[1:] or ["--help"]))
    from u3dc.__main__ import main
    main()
