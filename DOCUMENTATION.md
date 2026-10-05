# ZEISS TXM Importer for Dragonfly

Operating and developer guide · Plugin 0.4.1 · Windows, Dragonfly 2025.1

## 1. Purpose and status

This plugin reads processed ZEISS `.txm` reconstruction files directly into Dragonfly and sets their voxel-to-world geometry. Its purpose is to retain native intensity values and the spatial relationship encoded by supported ZEISS reconstruction metadata. It does not require conversion to TIFF or another intermediate volume format.

Before standalone imports are possible, the plugin requires either an eligible open original to use as a reference, or a completed saved calibration. There is no unverified metadata-only fallback.

Version 0.4.1 has passed full-volume live reference checks in Dragonfly 2025.1 on two original uint16 volumes (approximately 1000³ voxels each, 4x and 20x objectives), after which calibration was saved. This is live validation on one system and one reconstruction family, separate from the repository's synthetic tests.

## 2. What this plugin does and does not do

The importer opens source files read-only, checks metadata and image-stream structure, decodes image planes, creates a Dragonfly Channel, assigns geometry, and publishes the Channel after checks pass. It records provenance and validation information on the output Channel.

It imports **processed `.txm`** files. It neither reconstructs `.txrm` projection data nor writes new ZEISS files.

Position preservation means reproducing the selected original's transform or applying the supported calibrated metadata convention. It does not mean registering independently mounted specimens. The plugin does not perform landmark fitting, deformable registration, stitching, or correction for specimen remounting. A valid reference check establishes agreement with the selected original, not independent proof that the original's physical placement is correct.

## 3. Requirements and directory layout

Run the user interface inside Dragonfly. It relies on Dragonfly's `ORSModel`, NumPy, PyQt6, and plugin framework. A regular standalone Python interpreter can run the tests but cannot create real Dragonfly Channels.

The `olefile` 0.47 reader is bundled. No separate installation of that package is needed to import volumes.

Three locations have different jobs:

| Location | Purpose |
| --- | --- |
| This repository (any folder you clone or extract it to) | Editable source and documentation |
| Dragonfly's `pythonUserExtensions\Plugins\ZeissTXMImporter` directory | Installed copy loaded by Dragonfly |
| `%LOCALAPPDATA%\ORS\ZeissTXMImporter\calibration_v1.json` | Saved calibration for the current Windows account |

Depending on the Dragonfly distribution, the user extension root is typically one of:

```text
%LOCALAPPDATA%\ORS\Dragonfly2025.1\pythonUserExtensions
%LOCALAPPDATA%\Comet\Dragonfly2025.1\pythonUserExtensions
```

## 4. Run the source without installing

This is the simplest way to try the plugin, and remains useful when developing or diagnosing installation.

1. Clone or extract the complete repository into a normal folder. Do not launch a script while browsing inside an unopened ZIP archive.
2. Open Dragonfly and its **Utilities > Python Console**.
3. Run the block below and select `launch_dev.py` from the repository.
4. Confirm that the dialog title shows **ZEISS TXM Importer 0.4.1**.

```python
import runpy
from PyQt6.QtWidgets import QFileDialog

script, _ = QFileDialog.getOpenFileName(
    None, "Select launch_dev.py", "", "Python files (*.py)"
)
if script:
    runpy.run_path(script, run_name="__main__")
```

Once you know the path, you can launch directly. Replace the path with your own repository location:

```python
import runpy
runpy.run_path(r"C:\path\to\dragonfly_txm_importer_repo\launch_dev.py", run_name="__main__")
```

The development launcher uses a new Python module namespace on each run. Close the previous importer dialog before relaunching edited source so that it is clear which window belongs to which version. Running the source does not automatically update the installed plugin copy.

## 5. Install the File-menu entry

From the working importer dialog, click **Install File menu entry**. The installer copies the package into a selected `pythonUserExtensions\Plugins` folder. Save your Dragonfly work before restarting. After a successful restart and plugin discovery, the menu entry is **File > Import ZEISS TXM...**.

### Automatic discovery limitation in 0.4.1

The installer looks for a `pythonUserExtensions` ancestor in `sys.path`. If it cannot identify a unique location, it searches under `%LOCALAPPDATA%\ORS\Dragonfly*2025.1*`. It does not search the `%LOCALAPPDATA%\Comet\...` root used by some installations; on those systems a folder-selection dialog appears instead.

The dialog is a **folder selector**, titled “Select Dragonfly's pythonUserExtensions/Plugins folder.” It does not ask for the TXM input or plugin ZIP. Select the `Plugins` parent folder, not an existing `ZeissTXMImporter` child.

To find the right folder, check which of the roots in section 3 exists on your machine and contains a `pythonUserExtensions\Plugins` directory. The following prints Dragonfly's own search path, which normally includes the user extension root:

```python
import sys
print("\n".join(p for p in sys.path if "Dragonfly" in p))
```

An “Installed” message confirms the copy operation. It does not independently confirm that Dragonfly loaded the plugin after restart. If the menu entry is absent after a restart, use `launch_dev.py` to keep working and check Dragonfly's startup errors.

### Updates and backups

When replacing an existing installed copy, the installer moves it to `pythonUserExtensions\TXMImporterBackups\ZeissTXMImporter-<timestamp>`. Backups are outside `Plugins` to avoid duplicate discovery. If replacement fails after moving the old copy, the installer attempts to restore it.

After source changes, launch the updated source and install again, then restart Dragonfly.

### Uninstalling

The plugin leaves files in up to three places:

| Location | Contents | Remove? |
| --- | --- | --- |
| `pythonUserExtensions\Plugins\ZeissTXMImporter` | Installed plugin (File-menu entry) | Yes, to uninstall |
| `pythonUserExtensions\TXMImporterBackups` | Copies replaced by earlier installs | Optional |
| `%LOCALAPPDATA%\ORS\ZeissTXMImporter` | Saved calibration (`calibration_v1.json`) | Optional; back it up first if you may reinstall |

To uninstall by hand:

1. Save your work and close Dragonfly.
2. Delete the `ZeissTXMImporter` folder inside `pythonUserExtensions\Plugins` (see section 3 for where `pythonUserExtensions` lives). Delete only that folder; `Plugins` also holds other extensions.
3. Optionally delete `pythonUserExtensions\TXMImporterBackups` and `%LOCALAPPDATA%\ORS\ZeissTXMImporter`.
4. Start Dragonfly and confirm **File > Import ZEISS TXM...** is gone.

Or run this in PowerShell with Dragonfly closed. It checks both possible extension roots and lists each folder before removing it. Remove the last block if you want to keep the calibration:

```powershell
$roots = "$env:LOCALAPPDATA\ORS\Dragonfly2025.1", "$env:LOCALAPPDATA\Comet\Dragonfly2025.1"
foreach ($root in $roots) {
    foreach ($sub in "pythonUserExtensions\Plugins\ZeissTXMImporter", "pythonUserExtensions\TXMImporterBackups") {
        $path = Join-Path $root $sub
        if (Test-Path $path) { "Removing $path"; Remove-Item -Recurse -Force $path }
    }
}
# Calibration (omit to keep it for a future reinstall)
$calibration = "$env:LOCALAPPDATA\ORS\ZeissTXMImporter"
if (Test-Path $calibration) { "Removing $calibration"; Remove-Item -Recurse -Force $calibration }
```

Uninstalling does not change volumes already imported into Dragonfly sessions; they keep their geometry and the `ZeissTXMImporter` provenance metadata. If you only ever ran the plugin through `launch_dev.py` or the ZIP launcher, nothing was installed, and only the calibration folder may exist. The source repository can simply be deleted.

## 6. Calibration: purpose, storage, and reuse

Calibration records a consistent relationship between raw file indices, native Dragonfly voxel indices, and the supported metadata geometry. It is a software convention check, not a hardware calibration of the ZEISS instrument.

Standalone import requires two distinct geometry-header signatures at different voxel sizes. Both must have successful pixel checks, agree with the native geometry model, and share the same orientation convention. The originals must not be marked spatially transformed. Standalone calibration currently requires identity axis permutation, although flips may be present.

Profiles are stored separately by pixel dtype (`<u2` or `<f4`). Successful uint16 calibration does not enable float32 standalone import. The profile is not keyed by specimen or filename. It is also not a guarantee of compatibility across every ZEISS instrument or software version: new inputs must satisfy the metadata restrictions, and substantially different reconstruction families require independent validation.

Calibration path:

```text
%LOCALAPPDATA%\ORS\ZeissTXMImporter\calibration_v1.json
```

Use **Win + R**, paste `%LOCALAPPDATA%\ORS\ZeissTXMImporter`, and press Enter to open the folder. It persists across Dragonfly restarts, regardless of where the source is launched from.

The JSON contains a model identifier, dtype profiles, permutation/flips, reference filenames, geometry-header fingerprints, pixel sizes, sampling strides, and verified voxel counts. It contains no voxel images. Writes use a temporary file and replacement of the destination.

Back up this JSON together with placement reports. Do not edit its flags or counts to force acceptance. A conflicting observed orientation disables that profile. Preserve the evidence and resolve the mismatch before starting a fresh calibration.

## 7. First calibration on a new account or machine

Calibration is needed once per Windows account and pixel dtype.

1. Load two correctly placed, full-resolution originals of the same reconstruction family, acquired at different voxel sizes (for example, 4x and 20x scans), through Dragonfly's normal Open/Import workflow.
2. Do not use this plugin's own outputs as references. Previews made with version 0.3.0 also have known placement errors.
3. Open this plugin and click **Show open volumes**. Confirm both originals appear with their full dimensions.
4. Add the corresponding source `.txm` files. Adding a file only queues it; it does not create an open original reference.
5. Start with a **1/4 preview** if conserving memory. Every voxel in that sampled output will be checked. Choose full resolution when the purpose is to verify every source voxel.
6. If prompted, choose the correct original. Names help selection, but the pixels must still match.
7. Import both files. The first qualifying reference may request one more at a different voxel size. The second consistent reference should enable saved calibration, and the log reports **Calibration saved**.
8. Click **Save placement report** and retain the JSON with the calibration backup.

Renamed originals are supported. A unique full-dimension candidate can be tried; several candidates require a choice. Dimension matching alone is not accepted as proof. Plugin-generated Channels are excluded using structured provenance metadata.

## 8. Routine standalone imports

1. Open the plugin through the installed menu or `launch_dev.py`.
2. Add supported processed `.txm` files.
3. Choose a preview sampling stride, usually 4 for an initial check.
4. Import and inspect the results in Dragonfly, including their relative positions.
5. Save a placement report when documenting an important dataset or troubleshooting.
6. Import at full resolution when needed and memory permits.

If no eligible original is open, the saved calibration supplies the orientation convention. Each file's own metadata determines its origin and spacing. The original calibration specimen's absolute position is not copied to every future scan.

The output title ends in **[calibrated placement]** and the log reports **calibrated convention**. This is expected. It means the convention is reused, not that this particular file was independently compared with an original.

If a matching original is open, reference checking takes priority over the saved profile. For a clean standalone test, start a fresh Dragonfly session without originals and import a known supported file. Confirm the calibrated-placement label and compare against a saved placement report if available.

## 9. Preview sampling, memory, and cancellation

Supported strides are 1, 2, 4, and 8. A preview selects every nth voxel in each output axis. It does not average, normalize intensities, or interpolate. Small structures may disappear through sampling.

For each axis, output length is `ceil(full_length / stride)`. The first output voxel retains the corresponding full-resolution position, and voxel spacing increases by the stride. The last sampled voxel need not coincide with the original final voxel.

| Sampling | 1024³ output size | uint16 voxel allocation | float32 voxel allocation |
| --- | --- | ---: | ---: |
| Full | 1024³ | 2 GiB | 4 GiB |
| 1/2 | 512³ | 256 MiB | 512 MiB |
| 1/4 | 256³ | 32 MiB | 64 MiB |
| 1/8 | 128³ | 4 MiB | 8 MiB |

These are voxel-array sizes only. Dragonfly, rendering, open originals, and other objects need additional memory. The reader processes one image plane at a time, but the complete output Channel is allocated in memory. Full-volume reference checking adds work and is not a quick header-only operation.

Cancel removes the unfinished output. Previously completed imports remain. Repeating an import can create another Channel; this is not an in-place update of the prior output.

## 10. Spatial geometry and units

The model was derived from native Dragonfly transforms of original 4x and 20x volumes and confirmed by live calibration. Its world axes are `(-stage X, -stage Z, +stage Y)`. Output voxel basis directions are `(-X, -Y, +Z)`.

Let `W`, `H`, and `N` be full file width, height, and slice count; let `p` be header PixelSize in micrometres. The first voxel center in world micrometres is:

```text
X0 = -MeanSampleX + (W - 1) × p / 2
Y0 = -MeanSampleZ + (H - 1) × p / 2
Z0 =  MeanSampleY - (N - 1) × p / 2
```

The implementation converts these coordinates to metres. Standalone spacing is `float(format(p × 1e-6, '.6g')) × stride`; origin uses the full stored header precision. This reproduces the precision convention found in the original transforms.

For identity axis order, voxel indices `(i, j, k)` map to world coordinates as:

```text
X = X0 - i × spacing
Y = Y0 - j × spacing
Z = Z0 + k × spacing
```

Raw plane indexing is slice/row/column. Pixel permutation and flip detection is separate from world geometry; a correct bounding box alone does not establish correct pixel orientation. `CenterShift` is recorded but is not added again as a reconstructed-volume translation.

When using a reference, its actual voxel-to-world transform is used directly, with basis vectors scaled for the preview. The plugin reads the new Channel's transform back and checks all eight voxel-center corners against the target with a maximum allowed error of `1e-10 m`. This tolerance checks software transform agreement; it is not a statement of physical microscope accuracy.

## 11. Pixel verification and publication

The reference path first probes all 48 axis permutation/flip combinations. Exactly one arrangement must match. It then compares every imported voxel against the corresponding reference sample before publication. Sparse probes alone are not the final acceptance test.

Intensity comparison uses NumPy equality with matching NaNs treated as equal. There is no intensity scaling. The geometry setter rejects sheared or non-right-handed reference bases. An error in pixels, geometry, allocation, or cancellation removes the incomplete Channel.

A reference can match pixels and be copied successfully without qualifying for standalone calibration. Examples include a transformed original or an axis permutation outside the standalone model. The log distinguishes reference agreement from calibration eligibility.

## 12. Supported reconstruction metadata

The reader deliberately accepts a restricted family:

| Metadata or structure | Requirement |
| --- | --- |
| Extension | `.txm`, case-insensitive |
| `ImageInfo/DataType` | 5: uint16; 10: float32 |
| `ImageInfo/AcquisitionMode` | 10 |
| `ImageInfo/SampleStackOrientation` | 1 |
| `ReconSettings/ReconOperation` | 1 |
| `ReconSettings/ReconBinning` | 1 |
| `ReconSettings/RotationAngle` | 0 |
| `ReconSettings/ForceCropRect` | 0 |
| Crop rectangle coordinates | All zero |
| Dimensions and PixelSize | Positive |
| Slice coordinates | Finite and consistent with supported stage model |
| Image streams | Consecutive `ImageDataN/ImageM`, correct grouping and byte counts |

Where duplicate stage fields or cropped dimensions exist, they must agree with primary metadata within the coded tolerances. The reader rejects malformed compound files, missing or extra image streams, unsupported geometry, and inconsistent dimensions. A filename containing “trim” is not itself the criterion for accepting or rejecting a crop; actual metadata controls acceptance.

Do not bypass these checks to make a new file import. Extending support requires native references that establish the appropriate geometry and pixel convention for that case.

## 13. Reports and provenance

Use **Save placement report** to write a JSON report. It includes selected metadata, import results and failures, reference lookup diagnostics, open Channel geometry, calibration state, version, Python version, operating system, and UTC time.

| Field | Interpretation |
| --- | --- |
| `coordinate_mapping_validated` | True for an independently reference-checked result |
| `reference_voxels_verified` | Whether imported voxels were checked against an open reference |
| `verified_voxel_count` | Number checked; zero for standalone reuse |
| `voxel_orientation` | Detected or saved permutation and flips |
| `native_model_matches` | Whether a checked reference qualifies geometrically for the native model; null for standalone |
| `actual_voxel_to_world_m` | Read-back output transform |
| `target_voxel_to_world_m` | Intended transform |
| `geometry_readback_max_corner_error_m` | Largest output corner disagreement |
| `geometry_header_sha256` | Fingerprint of the metadata read for geometry validation |
| `source_files_modified` | False for this read-only importer |

The header fingerprint is not a checksum of the complete source voxel data. The report's top-level validated flag is true only if there are recorded import results and every recorded result has a true validated flag. A mixed session or standalone result can therefore make that flag false without indicating a failed import.

Imported Channels also receive JSON under the `ZeissTXMImporter` user-info key. Reports may contain sample filenames and identifiers; inspect them before sharing outside your project.

## 14. Troubleshooting

| Symptom | Meaning and action |
| --- | --- |
| `Headers checked` but no output | Only the queued file metadata has been inspected; start Import. |
| `Open volumes: NONE` | No original Channels are visible. Before calibration, load native originals normally. After calibration, check that the applicable profile is available. |
| No eligible reference | Check full dimensions, time points, and provenance. A preview or plugin output cannot bootstrap calibration. |
| One more different voxel size needed | First evidence was saved but the profile is not yet complete. Check another qualifying original with a different PixelSize. |
| Pixel verification failed | The candidate does not match the TXM throughout the selected grid. Check file identity and whether intensities were modified. |
| Orientation ambiguous | Multiple index arrangements match the probes, often with insufficiently distinctive data. Do not choose a flip by guesswork. |
| Calibration conflict | References produced inconsistent orientation conventions. Preserve reports and inspect before resetting. |
| Cannot read calibration | JSON is unreadable or has an unsupported model. Back up the file and investigate; do not fabricate a replacement profile. |
| Geometry readback differs | Dragonfly did not reproduce the requested transform within tolerance. Save diagnostics; do not accept the unfinished output. |
| Source metadata changed | Re-add the source after confirming which file should be imported. |
| Allocation failure | Use a coarser preview or free memory by closing unneeded volumes. |
| Bad local file header when launching ZIP | Could be a damaged archive or stale ZIP import state. Extract a fresh complete repository and run `launch_dev.py`; restart if necessary. |
| Installer asks for a file-like selection | This button uses a directory chooser. Select `pythonUserExtensions\Plugins`. If the title differs, capture it before proceeding. |
| No File-menu entry after restart | Copy success does not prove plugin discovery. Check destination and startup errors; use the source launcher meanwhile. |
| Old behavior after editing | Installed copy and source are separate. Relaunch source or reinstall and restart. |

When reporting a problem, include version, exact error/traceback, sampling stride, original dimensions, whether calibration was available, output of **Show open volumes**, and the placement report. A screenshot alone does not contain the voxel or transform evidence needed to establish pixel mapping.

## 15. Developer reference

| File | Responsibility |
| --- | --- |
| `launch_dev.py` | Fresh-namespace source launcher inside Dragonfly |
| `__main__.py` | ZIP entry point |
| `ZeissTXMImporter/core.py` | Read-only compound-file reader, metadata restrictions, geometry model |
| `ZeissTXMImporter/orientation.py` | Index orientation detection and oriented plane generation |
| `ZeissTXMImporter/adapter.py` | Reference discovery, Channel allocation, pixel checking, affine readback |
| `ZeissTXMImporter/calibration.py` | Profile eligibility and persistent evidence |
| `ZeissTXMImporter/ui.py` | Queue, sampling, logs, reports, installer action |
| `ZeissTXMImporter/install.py` | Target discovery, staged installation, backup/rollback |
| `ZeissTXMImporter/ZeissTXMImporter.py` | Dragonfly plugin class and File-menu registration |
| `ZeissTXMImporter/mainform.py` | Plugin form integration |
| `tests/test_importer.py` | Synthetic file and mocked Dragonfly tests |
| `build_plugin.py` | Distribution ZIP builder |

The version number is defined in both `ZeissTXMImporter/core.py` (`VERSION`) and `ZeissTXMImporter/__init__.py` (`__version__`); keep them in step.

### Testing

From the repository root, in a separate Python environment (not Dragonfly's):

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite contains 19 test methods. Coverage includes synthetic OLE files, both dtypes, asymmetric dimensions, all 48 orientations, full sampled-grid comparisons, mismatches between probe points, ambiguous references, provenance placeholders, geometry conventions, source immutability, cancellation, calibration eligibility/conflicts, and installation backups. Two optional tests consume real header and placement reports via the `TXM_HEADER_REPORT_DIR` and `TXM_PLACEMENT_REPORT` environment variables and are skipped when those are not set.

Mocked ORS tests do not prove live plugin discovery or behavior in every Dragonfly release.

### Packaging and source control

Run `py build_plugin.py` from the repository root to produce `dist/dragonfly_txm_importer.zip`. After changing code, test the relevant behavior, launch the source in Dragonfly, and reinstall the validated version.

Keep large TXM inputs and machine-specific calibration/report evidence out of source commits; `.gitignore` excludes them by default.

### Implementation invariants

- Keep source TXM files read-only.
- Preserve voxel values and supported dtypes; do not add normalization or interpolation to the import path.
- Keep raw-array orientation distinct from voxel-to-world geometry.
- Preserve metre/micrometre conversion, voxel-center offsets, and the documented spacing precision convention.
- Do not enable calibration by weakening evidence requirements or manually setting success flags.
- Retain strict metadata rejection for unsupported reconstruction variants until reference evidence supports an extension.
- Do not let this plugin's outputs become independent original references.
- Maintain cleanup of incomplete Channels on errors and cancellation.
- Keep installed backups outside the scanned Plugins directory.
- Report standalone reuse distinctly from independent reference checking.

### Changes needing additional validation

Adding reconstruction rotations, crop offsets, binning, dtype support, another Dragonfly release, or a different axis convention requires new reference evidence. Maintain explicit units and voxel-center conventions. Test both pixel correspondence and world geometry, including asymmetric synthetic data, sampled and full grids, reference mismatch rejection, and world-coordinate readback. Preserve the difference between a directly checked result and one using a saved convention.

A useful installer improvement would be to discover the `%LOCALAPPDATA%\Comet\...` extension root automatically, after confirming how Dragonfly locates it.

## 16. License and dependency notices

This project is released under the MIT License; see `LICENSE`.

The bundled `olefile` 0.47 reader keeps its own BSD-style license and notices in `ZeissTXMImporter/vendor/OLEFILE_LICENSE.txt` and the bundled `olefile` directory. Dragonfly is a separately installed commercial application and is not distributed with this project.
