"""Run this file inside Dragonfly to launch the current repository source."""
import importlib
from pathlib import Path
import sys
import types
import uuid

try:
    import ORSModel
except ImportError as exc:
    raise RuntimeError("Run launch_dev.py in Dragonfly's Python Console.") from exc

# A new namespace on each run allows source edits to be loaded while leaving
# already registered plugins and already open importer windows intact.
package_name = "_ZeissTXMImporterDev_" + uuid.uuid4().hex
package = types.ModuleType(package_name)
package.__path__ = [str(Path(__file__).resolve().parent / "ZeissTXMImporter")]
sys.modules[package_name] = package
importlib.import_module(package_name + ".ui").launch()
