"""Persist a convention only after two independent native-reference checks."""
from pathlib import Path
import json
import os
import tempfile
from .core import TXMError
from .orientation import validate_orientation

MODEL = "dragonfly-2025.1-zeiss-zero-rotation-v1"


def default_path():
    base = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else Path.home()/".config"
    return base/"ORS"/"ZeissTXMImporter"/"calibration_v1.json"


def load(path=None):
    path = Path(path) if path is not None else default_path()
    if not path.exists():
        return {"model": MODEL, "profiles": {}}
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("model") != MODEL or not isinstance(result.get("profiles"), dict):
            raise ValueError("Unknown calibration model")
        return result
    except (OSError, ValueError, AttributeError) as error:
        raise TXMError("Cannot read calibration: " + str(error))


def usable(profile):
    if not isinstance(profile, dict) or profile.get("conflict"):
        return False
    try:
        perm, _ = validate_orientation(profile)
        evidence = profile["references"]
        # Standalone model currently established for the original file axes.
        return (perm == (0, 1, 2) and
                len({r["geometry_header_sha256"] for r in evidence}) >= 2 and
                len({r["pixel_um"] for r in evidence}) >= 2 and
                all(r["native_model_matches"] is True and r["verified_voxel_count"] > 0 for r in evidence))
    except (KeyError, TypeError, TXMError):
        return False


def get_profile(meta, path=None):
    profile = load(path)["profiles"].get(meta.dtype)
    return profile if usable(profile) else None


def record(report, path=None):
    if not report.get("native_model_matches") or not report.get("reference_voxels_verified"):
        return False
    path = Path(path) if path is not None else default_path()
    data = load(path)
    orientation = report["voxel_orientation"]
    perm, _ = validate_orientation(orientation)
    if perm != (0, 1, 2):
        return False
    profile = data["profiles"].setdefault(report["dtype"], dict(orientation, references=[]))
    if any(profile[k] != orientation[k] for k in ("permutation", "flips")):
        profile["conflict"] = True
    evidence = {k: report[k] for k in ("name", "geometry_header_sha256", "pixel_um",
                                      "native_model_matches", "verified_voxel_count", "sampling_stride")}
    profile["references"] = [r for r in profile["references"]
                              if r["geometry_header_sha256"] != evidence["geometry_header_sha256"]] + [evidence]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="calibration-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return usable(profile)
