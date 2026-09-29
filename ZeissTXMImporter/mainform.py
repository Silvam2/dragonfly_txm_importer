from PyQt6 import QtWidgets
from ORSServiceClass.windowclasses.orsabstractwindow import OrsAbstractWindow
from OrsLibraries.workingcontext import WorkingContext
from .ui import ImportPanel
from .core import VERSION


class MainForm(OrsAbstractWindow):
    def __init__(self, implementation, parent=None):
        super().__init__(implementation, parent)
        self.setWindowTitle("ZEISS TXM Importer " + VERSION)
        layout = QtWidgets.QVBoxLayout(self)
        self.panel = ImportPanel(self)
        layout.addWidget(self.panel)
        self.resize(1050, 640)
        WorkingContext.registerOrsWidget("ZeissTXMImporter", self.getImplementation(), "MainForm", self)

    def closeEvent(self, event):
        if self.panel.busy:
            event.ignore()
        else:
            super().closeEvent(event)
