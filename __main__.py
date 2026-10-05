"""Run this ZIP with runpy inside Dragonfly's Python Console."""
try:
    import ORSModel
except ImportError as exc:
    raise RuntimeError("Run this ZIP in Dragonfly 2025.1: Tools > Python Console.") from exc

# An isolated session name prevents an already installed or running copy of the
# plugin from shadowing this ZIP. No deletion/reloading of Dragonfly's
# registered plugin modules is needed.
import importlib
from pathlib import Path
import sys
import types

session_package = "_ZeissTXMImporterPreview_041"
if session_package not in sys.modules:
    package = types.ModuleType(session_package)
    package.__path__ = [str(Path(__file__).parent / "ZeissTXMImporter")]
    sys.modules[session_package] = package
importlib.import_module(session_package + ".ui").launch()
