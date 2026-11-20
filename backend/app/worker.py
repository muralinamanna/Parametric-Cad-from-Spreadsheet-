"""Run with a Python interpreter matching the FreeCAD module's ABI."""
import sys

try:
    import PySide
except ModuleNotFoundError:
    import PySide2
    from PySide2 import QtCore, QtGui, QtWidgets, QtSvg
    sys.modules.update({"PySide": PySide2, "PySide.QtCore": QtCore,
                        "PySide.QtGui": QtGui, "PySide.QtWidgets": QtWidgets,
                        "PySide.QtSvg": QtSvg})

import cad

if __name__ == "__main__":
    cad.main(sys.argv[1])
