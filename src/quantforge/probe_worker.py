"""Compatibility entry point for the targeted execution worker."""

from pathlib import Path
import runpy


def main():
    worker = Path(__file__).with_name("runtime") / "probe_worker.py"
    runpy.run_path(str(worker), run_name="__main__")


if __name__ == "__main__":
    main()
