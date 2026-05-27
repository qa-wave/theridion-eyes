"""PyInstaller entry point.

PyInstaller's `--name` flag produces an executable that runs whatever this
file invokes. We just delegate to the package's main(); having a tiny
script here means we don't have to pass a module spec at bundle time.
"""

from theridion_sidecar.main import main

if __name__ == "__main__":
    main()
