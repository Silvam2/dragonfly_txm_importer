# Dragonfly ZEISS TXM Importer

A Dragonfly plugin that imports processed ZEISS `.txm` reconstruction volumes
directly, preserving native intensity values and voxel-to-world placement.
Version **0.4.1**, targeting Windows Dragonfly 2025.1.

The plugin checks pixels and geometry against open original volumes and saves
a calibration so later supported files can be imported standalone.

## Get the source

Clone or extract this repository into any normal folder, for example:

```powershell
git clone <repository-url> dragonfly_txm_importer_repo
```

The `ZeissTXMImporter` directory, `launch_dev.py`, and this README should sit
directly inside the repository folder. Do not run scripts from inside an
unopened ZIP archive.

## Run the source in Dragonfly

Open **Tools > Python Console** and run the block below, selecting
`launch_dev.py` from this repository:

```python
import runpy
from PyQt6.QtWidgets import QFileDialog

script, _ = QFileDialog.getOpenFileName(None, "Select launch_dev.py", "", "Python files (*.py)")
if script:
    runpy.run_path(script, run_name="__main__")
```

The dialog title should show **ZEISS TXM Importer 0.4.1**. The development
launcher loads the source in a fresh module namespace each time. Close an old
importer dialog before launching edited code.

Click **Install File menu entry** to copy the plugin into Dragonfly's
`pythonUserExtensions\Plugins` folder, then restart Dragonfly and use
**File > Import ZEISS TXM...**. Later repository edits require reinstalling
that copy, or using the development launcher above.

For the first calibration, keep two correctly placed full-resolution original
volumes at different voxel sizes (for example 4x and 20x) open. See
[DOCUMENTATION.md](DOCUMENTATION.md) for installation, calibration, geometry,
and troubleshooting, and [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for a shorter
overview.

## Uninstall

1. Close Dragonfly.
2. Delete the installed plugin folder, `pythonUserExtensions\Plugins\ZeissTXMImporter`.
   Depending on your Dragonfly distribution it is under
   `%LOCALAPPDATA%\ORS\Dragonfly2025.1\` or `%LOCALAPPDATA%\Comet\Dragonfly2025.1\`.
   Delete only that folder, not the rest of `Plugins`.
3. Optional: delete `pythonUserExtensions\TXMImporterBackups`, which holds
   copies replaced by earlier installs.
4. Optional: delete `%LOCALAPPDATA%\ORS\ZeissTXMImporter`, which holds the saved
   calibration. Keep a copy if you may reinstall, or you will need to
   calibrate again.

Volumes already imported into your Dragonfly sessions are not affected. If you
only used `launch_dev.py` and never clicked **Install File menu entry**, there
is nothing to uninstall besides the optional calibration folder. See
[DOCUMENTATION.md](DOCUMENTATION.md#uninstalling) for a PowerShell script that
does steps 2–4.

## Tests and packaging

To run the tests using a separate Python installation, from the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests mock Dragonfly's API. Two optional evidence tests skip unless real
header/placement reports are supplied through the `TXM_HEADER_REPORT_DIR` and
`TXM_PLACEMENT_REPORT` environment variables. No scan data is included in this
repository.

Build the distributable plugin ZIP with:

```powershell
py build_plugin.py
```

The result is `dist/dragonfly_txm_importer.zip`. `TEST_RESULTS.txt` records
validation of the current version; update it after changes.

## Files

- `ZeissTXMImporter/`: plugin, reader, geometry, calibration, and interface code.
- `tests/`: synthetic file fixtures and automated tests.
- `DOCUMENTATION.md`: full operating and developer guide.
- `docs/USER_GUIDE.md`: short user overview.
- `launch_dev.py`: run the current repository source inside Dragonfly.
- `build_plugin.py`: package the plugin without caches or scan data.
- `__main__.py`: launcher used by the distributable plugin ZIP.

## Limitations

A reference check establishes agreement with an open original; it is not
independent physical registration. Standalone imports reuse a calibrated
convention and are labelled **[calibrated placement]**. Only a restricted,
validated family of reconstruction metadata is accepted.

## License

Released under the [MIT License](LICENSE). The bundled `olefile` 0.47 keeps its
upstream license in `ZeissTXMImporter/vendor/OLEFILE_LICENSE.txt`.
