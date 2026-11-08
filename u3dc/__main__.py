"""Punto de entrada: sin argumentos abre la interfaz gráfica; con argumentos, modo consola."""
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] in ("convert", "matrix", "info", "--version", "-h", "--help"):
        from .cli import main as cli_main
        sys.exit(cli_main(sys.argv[1:]))
    from .ui.app import run
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
