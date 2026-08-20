"""PyInstaller entry point.

__main__.py uses relative imports, which fail when PyInstaller executes it as a
top-level script — import the package entry absolutely and delegate.
"""

import sys

try:
    # Frozen-only crash guard: PySide6's shibokensupport inspects every module
    # imported after shiboken6 loads. six.moves modules carry origin=None specs,
    # so importlib's repr path reads spec.loader._path — which six's meta-path
    # importer lacks -> AttributeError when pystray imports six.moves.queue.
    import six

    if not hasattr(six._importer, "_path"):
        six._importer._path = []
except ImportError:
    pass

from after_scope.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
