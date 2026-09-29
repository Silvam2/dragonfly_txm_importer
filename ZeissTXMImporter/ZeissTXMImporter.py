"""ZEISS TXM reconstruction import with checked reference calibration."""
from ORSServiceClass.OrsPlugin.orsPlugin import OrsPlugin
from ORSServiceClass.OrsPlugin.uidescriptor import UIDescriptor
from ORSServiceClass.decorators.infrastructure import menuItem
from ORSServiceClass.actionAndMenu.menu import Menu
from .core import VERSION


class ZeissTXMImporter(OrsPlugin):
    multiple = False
    UIDescriptors = [UIDescriptor(name="MainForm", title="ZEISS TXM Importer " + VERSION,
                                 dock="Floating", tab="Main", modal=False,
                                 collapsible=True, movable=True, floatable=True)]

    @classmethod
    def getMainFormClass(cls):
        from .mainform import MainForm
        return MainForm

    @classmethod
    @menuItem("File")
    def importerMenu(cls):
        return Menu(id_="ZeissTXMImporter_Open", title="Import ZEISS TXM...",
                    section="ZeissTXMImporter", action=cls.getActionStringForStartupDefault())
