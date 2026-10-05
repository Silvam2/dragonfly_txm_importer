# ZEISS TXM Importer 0.4.1 for Dragonfly 2025.1

This plugin imports processed ZEISS `.txm` reconstruction volumes into
Dragonfly, preserving native intensity values and voxel-to-world placement. It
compares imports with open original volumes and saves a calibration for later
standalone imports of the supported TXM reconstruction family. Native `.txm`
files are read directly and opened read-only.

## First run and calibration

1. Open two correctly placed, full-resolution original volumes of the same
   reconstruction family at different voxel sizes (for example 4x and 20x
   scans) through Dragonfly's normal Open/Import workflow. Do not use previews
   made by this plugin, or by version 0.3.0, as originals.
2. Close any older importer dialog. You do not need to restart Dragonfly to run
   the ZIP; its launcher avoids reusing an older version's Python code.
3. Use **Utilities > Python Console** to execute this complete block, and select
   `dragonfly_txm_importer.zip`:

```python
import runpy
from PyQt6.QtWidgets import QFileDialog
txm_zip, _ = QFileDialog.getOpenFileName(None, "Select TXM importer ZIP", "", "ZIP files (*.zip)")
if txm_zip:
    runpy.run_path(txm_zip, run_name="__main__")
```

4. The dialog title must show **0.4.1**. Add the `.txm` files that match the
   open originals. Keep **1/4 preview** selected and click **Import previews**.
5. A successful comparison labels each new volume **[reference checked]**.
   The log gives the number of verified voxels. After two consistent references
   at different voxel sizes, it reports **Calibration saved**.
6. Click **Save placement report**. The report records both reference transforms,
   detected pixel order, checked voxel counts, and calibration status.

After successful calibration, supported files with the same pixel type can be
imported without an open original. These imports are labelled **[calibrated
placement]**, because the convention has been checked but the new file has not
been independently compared with its own original.

Use **Full resolution** after the preview check if needed. **Install File menu
entry** installs/updates the plugin for future sessions. Restart Dragonfly after
installation and use **File > Import ZEISS TXM**. An older installed copy is
backed up outside the Plugins folder.

To open the `Plugins` folder, paste one of these into the File Explorer address
bar, depending on your Dragonfly distribution:

```text
%LOCALAPPDATA%\ORS\Dragonfly2025.1\pythonUserExtensions\Plugins
%LOCALAPPDATA%\Comet\Dragonfly2025.1\pythonUserExtensions\Plugins
```

## What is checked

- A reference is selected by its original filename/title and full dimensions.
  Plugin-produced objects are excluded. Multiple matching originals cause a
  clear error, rather than an arbitrary selection.
- The plugin compares raw TXM samples against all 48 axis-permutation/flip
  combinations. Exactly one combination must match.
- It then compares **every imported voxel** with the corresponding voxel of
  the reference, with no intensity normalization or resampling. For a 1/4
  preview this means every voxel on the sampled grid, not every full-volume voxel.
  Full-resolution import checks the entire volume.
- It copies the reference voxel-to-world transform, retaining the first voxel
  and multiplying spacing by the preview stride. Geometry is read back from
  Dragonfly and checked at all eight volume corners with a 1e-10 m tolerance.
- A pixel mismatch, ambiguous orientation, or geometry mismatch aborts the
  unfinished import. Completed Channels remain.
- Standalone calibration requires two distinct header signatures at different
  voxel sizes, consistent pixel directions, no transform of the originals,
  and agreement with the corrected native geometry model. Conflicting
  observations disable standalone calibration.

A reference check establishes agreement with the chosen open original. It
cannot establish that the original itself is physically registered correctly.
No new landmark fitting, image registration, or specimen-remount correction
is performed.

## Geometry model

Native original 4x and 20x Channels establish world axes
`(-stage X, -stage Z, +stage Y)` and voxel-axis directions `(-X, -Y, +Z)`.
Their first-voxel positions, in micrometres, are reproduced by:

```text
world X = -MeanSampleX + (ImageWidth  - 1) * PixelSize / 2
world Y = -MeanSampleZ + (ImageHeight - 1) * PixelSize / 2
world Z =  MeanSampleY - (NoOfImages  - 1) * PixelSize / 2
```

Their spacing uses six significant digits, while their first-voxel calculation
uses the full header PixelSize. This behavior is included in the standalone
model and must agree with both live references before calibration is enabled.
When an original is open, its actual transform is used directly.

Version 0.3.0 used positive stage axes, transposed the array, and used an N/2
rather than (N-1)/2 transverse offset. Those previews should not be used for
placement measurements. Re-importing creates new objects; it does not repair
previously imported objects in place.

## Supported files and limits

The strict geometry whitelist is retained: processed `.txm`, acquisition mode
10, stack orientation 1, reconstruction operation 1, reconstruction binning 1,
zero rotation, zero explicit crop rectangle, regular slice coordinates, and
consistent metadata. Supported types are uint16 (5) and float32 (10), with a
separate calibration for each type. Native reference matching supports all
48 index arrangements; standalone calibration currently requires the native
array to retain the file's slice/row/column axes, allowing sign reversals.

This build reads numbered `ImageDataN/ImageM` compound-file streams. Unsupported
rotation/crop/mode combinations, malformed metadata, and missing image data
are rejected. It does not reconstruct `.txrm` projections or write ZEISS files.

Preview is stride sampling without averaging or interpolation. Full-resolution
1024-cubed uint16 data needs 2 GiB of voxel memory, plus Dragonfly overhead.
A 1/4 preview needs 32 MiB. Decoding uses one image plane at a time; reference
checks use the original Channel's existing NumPy view, not another full copy.

Calibration is stored in
`%LOCALAPPDATA%\ORS\ZeissTXMImporter\calibration_v1.json` on Windows. It includes
filenames, relevant metadata fingerprints, and validation counts, not voxel
images. Removing this file resets calibration. A conflict requires reviewing
reference conventions before starting a fresh calibration.

The bundled `olefile` 0.47 reader needs no installation or internet connection.
NumPy and PyQt6 come from Dragonfly. The source code and tests are included.

## Uninstall

1. Close Dragonfly.
2. Delete only the `pythonUserExtensions\Plugins\ZeissTXMImporter` folder. It is
   under `%LOCALAPPDATA%\ORS\Dragonfly2025.1\` or
   `%LOCALAPPDATA%\Comet\Dragonfly2025.1\`, depending on your Dragonfly
   distribution.
3. Optional: delete `pythonUserExtensions\TXMImporterBackups` (copies replaced by
   earlier installs) and `%LOCALAPPDATA%\ORS\ZeissTXMImporter` (the saved
   calibration; back it up first if you may reinstall).

Volumes already imported into Dragonfly are not affected. If the plugin was only
run from the ZIP and never installed, only the calibration folder may exist.

## Validation and technical sources

The tests cover synthetic OLE files, asymmetric dimensions, all 48 pixel
orientations, strided comparisons, an image mismatch missed by sparse probes,
reference ambiguity, calibration conflicts, both origin conventions, source
immutability, cancellation, corrupt metadata, and installation backups. Real
scan reports are not included in the repository.

Version 0.4.1 has passed full-volume live reference checks against two original
uint16 volumes in Dragonfly 2025.1, after which calibration was saved. New
reconstruction families should still be checked against an open original first.

Run the included tests outside Dragonfly with Python and NumPy:

```text
python -m unittest discover -s tests -v
```

Optional evidence tests use `TXM_HEADER_REPORT_DIR` for a folder of header
reports and `TXM_PLACEMENT_REPORT` for a placement-report JSON; they are skipped
when those variables are not set.

This plugin is released under the MIT License; see `LICENSE`.

Official Dragonfly 2025.1 API references:
- https://dev.theobjects.com/dragonfly_2025_1_release/Documentation/Extensions/plugins.html
- https://dev.theobjects.com/dragonfly_2025_1_release/ORSServiceClass/decorators/sphinxIndexdecorators.html
- https://dev.theobjects.com/dragonfly_2025_1_release/Documentation/CodeSnipets/UsingNumpyArrays/extractNumpyArrayFromChannel.html
- https://dev.theobjects.com/dragonfly_2025_1_release/ORSModel/sphinxIndexORSModelClasses/sphinxIndexORSModelBox.html

Format-field references (independent implementation):
- https://github.com/ome/bioformats/blob/develop/components/formats-gpl/src/loci/formats/in/ZeissXRMReader.java
- https://github.com/data-exchange/dxchange/blob/master/dxchange/reader.py

Bundled dependency: https://github.com/decalage2/olefile, version 0.47.
Full notices remain in `ZeissTXMImporter/vendor/OLEFILE_LICENSE.txt` and the
bundled package. Dragonfly is separately installed.
