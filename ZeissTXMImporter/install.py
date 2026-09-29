"""Install only this plugin into the current user's extension directory."""
from pathlib import Path
import os
import shutil
import sys
import tempfile
import time
import zipfile


def candidate_directory():
    candidates = set()
    for entry in sys.path:
        path = Path(entry)
        for parent in (path, *path.parents):
            if parent.name.casefold() == "pythonuserextensions":
                candidates.add(parent / "Plugins")
    if len(candidates) == 1:
        return candidates.pop()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates = set((Path(local) / "ORS").glob("Dragonfly*2025.1*/pythonUserExtensions/Plugins"))
    return next(iter(candidates)) if len(candidates) == 1 else None


def install_to(parent):
    parent = Path(parent)
    if parent.name.casefold() != "plugins" or parent.parent.name.casefold() != "pythonuserextensions":
        raise ValueError("Select the Plugins folder inside Dragonfly's pythonUserExtensions folder.")
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / "ZeissTXMImporter"
    source = Path(__file__).parent
    if source.is_dir() and source.resolve() == destination.resolve():
        return str(destination), None
    staging = Path(tempfile.mkdtemp(prefix="txm-install-", dir=str(parent.parent)))
    staged = staging / "ZeissTXMImporter"
    backup = None
    try:
        if source.is_dir():
            shutil.copytree(source, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            archive = next((p for p in Path(__file__).parents if p.is_file() and p.suffix.lower() == ".zip"), None)
            if archive is None:
                raise RuntimeError("Cannot locate the downloaded plugin ZIP.")
            with zipfile.ZipFile(archive) as bundle:
                for item in bundle.infolist():
                    parts = Path(item.filename).parts
                    if not parts or parts[0] != "ZeissTXMImporter" or item.is_dir():
                        continue
                    if ".." in parts or Path(item.filename).is_absolute():
                        raise ValueError("Invalid archive member.")
                    target = staging.joinpath(*parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(bundle.read(item))
        if not (staged / "ZeissTXMImporter.py").is_file():
            raise RuntimeError("The plugin package is incomplete.")
        if destination.exists():
            # Keep backups OUTSIDE Plugins so Dragonfly will not load them twice.
            backups = parent.parent / "TXMImporterBackups"
            backups.mkdir(exist_ok=True)
            backup = backups / ("ZeissTXMImporter-" + str(time.time_ns()))
            destination.rename(backup)
        try:
            staged.rename(destination)
        except BaseException:
            if backup is not None:
                backup.rename(destination)
            raise
        return str(destination), str(backup) if backup else None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
