# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Dragonfly 2025.1 (Windows) plugin that imports processed ZEISS `.txm` reconstruction volumes directly, keeping native voxel values and voxel-to-world placement. The plugin runs inside Dragonfly's embedded Python (`ORSModel`, `ORSServiceClass`, PyQt6, NumPy). It cannot run against real Dragonfly on this Linux box; only the mocked test suite runs here. `DOCUMENTATION.md` is the full operating and developer guide; section 15 lists per-file responsibilities.

## Commands

Tests use `unittest` (not pytest) and need only NumPy:

```bash
python3 -m unittest discover -s tests -v                       # all tests
python3 -m unittest discover -s tests -k test_float32_preserves_values   # one test
```

- `ORSModel` is replaced per test by `MockChannel`/`V` via `patch.dict(sys.modules, ...)`. The tests load `ZeissTXMImporter/` as the namespace package `txm_test_package`, so modules that import Dragonfly at module level (`ZeissTXMImporter.py`, `mainform.py`, `ui.py`) are not imported by the tests.
- Synthetic `.txm` fixtures are real compound files written by `write_cfb()` in the test file; `streams_for_volume()` defines the metadata streams a valid file must have.
- Two evidence tests skip unless `TXM_HEADER_REPORT_DIR` / `TXM_PLACEMENT_REPORT` point at real header/placement report JSON.
- Mocked tests do not prove live Dragonfly behavior. `TEST_RESULTS.txt` records what was validated per version (tests and live checks in Dragonfly); update it after changes.

Build the distributable ZIP (writes `dist/dragonfly_txm_importer.zip`; `docs/USER_GUIDE.md` becomes the ZIP's `README.md`, and `__main__.py` is its entry point):

```bash
python3 build_plugin.py
```

Inside Dragonfly, `launch_dev.py` loads the source under a fresh `uuid` package name on every run so edits take effect without restarting; `__main__.py` does the same for the ZIP under a fixed name. **Install File menu entry** in the dialog (`install.py`) copies the package into `pythonUserExtensions\Plugins\ZeissTXMImporter`.

## Architecture

Import pipeline, in dependency order (`core` has no Dragonfly dependency; `adapter` imports `ORSModel` lazily inside functions):

1. `core.py`: `TXMFile` opens the OLE compound file read-only through the bundled `vendor/olefile`. `decode_metadata()` is a strict whitelist: it rejects anything outside the one validated reconstruction family (uint16/float32 only, acquisition mode 10, no rotation, binning 1, no crop, slice positions fitting the stage model). `Metadata` holds the geometry model: world axes `[-stage X, -stage Z, +stage Y]`, origin at voxel centers, spacing rounded to 6 significant digits to match Dragonfly's originals. `geometry_header_sha256` fingerprints the geometry streams.
2. `orientation.py`: `detect_orientation()` probes a 9×9×9 grid against an open reference array over all 48 permutation/flip combinations and requires exactly one match. `oriented_planes()` then yields planes in the reference's array order.
3. `adapter.py`: `import_txm()` has two modes:
   - **Reference mode**: an open original Channel is found (`find_reference`/`inspect_references`, which exclude this plugin's own outputs via the `ZeissTXMImporter` user-info tag). Every output voxel is compared with the reference, and the reference's world affine is copied. Title suffix `[reference checked]`.
   - **Calibrated mode**: no reference, but a usable saved profile exists; `Metadata.native_affine()` is applied. Title suffix `[calibrated placement]`.
   With neither, it raises; there is no metadata-only fallback. `set_affine()` writes the geometry, then reads it back and fails if any volume corner is off by more than 1e-10 m. On any error the partial Channel is deleted.
4. `calibration.py`: a profile per dtype in `%LOCALAPPDATA%\ORS\ZeissTXMImporter\calibration_v1.json` (falls back to `~/.config/...` off Windows). `usable()` requires ≥2 reference checks with distinct header hashes **and** distinct pixel sizes, identity permutation, `native_model_matches`, and no conflict. `record()` writes atomically via temp file + `os.replace`.
5. `ui.py` (queue, sampling stride 1/2/4/8, logs, report export, install button), `mainform.py` + `ZeissTXMImporter.py` (Dragonfly plugin class and File-menu registration).

## Rules to preserve

From `DOCUMENTATION.md` §15 "Implementation invariants":

- Never write to source TXM files; no normalization or interpolation of voxel values.
- Keep raw-array orientation (`orientation.py`) separate from voxel-to-world geometry (`core.Metadata`).
- Do not relax the `decode_metadata()` whitelist, or the `calibration.usable()` evidence requirements, without new reference evidence from real files. Rotations, crops, binning, new dtypes, other Dragonfly releases, or another axis convention all need it.
- Plugin outputs must never qualify as references, and standalone (calibrated) imports must stay labelled distinctly from reference-checked ones.
- Installer backups go in `pythonUserExtensions\TXMImporterBackups`, outside `Plugins`, so Dragonfly does not load them twice.
- The version is defined twice: `VERSION` in `core.py` and `__version__` in `__init__.py`. Keep them in step; `__main__.py`'s session package name (`_ZeissTXMImporterPreview_041`) also encodes it.
- Keep `.txm`/`.txrm` data, calibration JSON, and placement/header reports out of commits (`.gitignore` covers them).
