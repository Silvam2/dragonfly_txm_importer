# Dragonfly ZEISS TXM Importer

Repository source for version **0.4.0**, targeting Windows Dragonfly 2025.1.
The plugin imports native processed `.txm` volumes, checks pixels and geometry
against open originals, and saves a calibration for subsequent supported imports.

Extract this archive directly into:

```text
U:\dragonfly\_txm\_importer
```

The `ZeissTXMImporter` directory and this README should sit immediately inside
`_importer`, without another enclosing folder.

## Repository setup

In PowerShell, with Git installed:

```powershell
Set-Location 'U:\dragonfly\_txm\_importer'
git init
git status
```

The included `.gitignore` excludes scan volumes, calibration files, generated
ZIPs, diagnostic reports, and Python caches. Review the files before making
your first commit or adding a remote.

## Run the current source in Dragonfly

Open **Tools > Python Console** and run:

```python
import runpy
runpy.run_path(r"U:\dragonfly\_txm\_importer\launch_dev.py", run_name="__main__")
```

The development launcher loads the source from this folder in a fresh module
namespace each time. Close an old importer dialog before launching edited code.
Installing the File menu entry copies the plugin into Dragonfly's extension
directory; later repository edits require reinstalling that copy, or using
the development launcher above.

For the first calibration, keep the original full-resolution 4x and 20x
volumes open. See [the user guide](docs/USER_GUIDE.md) for supported files,
validation, installation, and calibration steps.

## Tests and packaging

To run the tests using a separate Python installation, from the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests mock Dragonfly's API. Two optional evidence tests skip unless the
original header/placement reports are supplied through the environment variables
documented in the user guide. The user reports and actual volumes are not
included in this repository.

Build the distributable plugin ZIP with:

```powershell
py build_plugin.py
```

The result is `dist/dragonfly_txm_importer.zip`. The historical validation notes
in `TEST_RESULTS.txt` describe the supplied version; update them after changes.

## Files

- `ZeissTXMImporter/`: plugin, reader, geometry, calibration, and interface code.
- `tests/`: synthetic file fixtures and automated tests.
- `docs/USER_GUIDE.md`: setup, behavior, geometry model, and limitations.
- `launch_dev.py`: run the current repository source inside Dragonfly.
- `build_plugin.py`: package the plugin without caches or scan data.
- `__main__.py`: launcher used by the distributable plugin ZIP.

Bundled `olefile` 0.47 retains its upstream notices in
`ZeissTXMImporter/vendor/OLEFILE_LICENSE.txt`. No project-wide open-source
license has been selected; choose one before public distribution if desired.

Version 0.4.0 still requires the live reference check in the user's Dragonfly
session. Agreement with an original is not independent physical registration.
