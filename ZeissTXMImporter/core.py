"""Independent, read-only reader for the inspected ZEISS reconstruction layout.

Pixel decoding is independent of Dragonfly. The geometry model was derived from
two original Channel transforms. Pixel orientation is checked at runtime against
open references before allowing a stored standalone calibration. Do not extend
the geometry whitelist without suitable reference files.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import math
import re
import struct

import numpy as np
from .vendor import olefile

VERSION = "0.4.1"


class TXMError(ValueError):
    pass


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Metadata:
    name: str
    file_bytes: int
    width: int
    height: int
    slices: int
    dtype: str
    pixel_um: float
    mean_xyz_um: tuple
    first_slice_y_um: float
    center_shift: float
    geometry_header_sha256: str

    def dimensions_xyz(self, stride=1):
        if type(stride) is not int or stride not in (1, 2, 4, 8):
            raise TXMError("Sampling must be 1, 2, 4, or 8.")
        # Native reference Channels retain file dimensions [column, row, slice].
        return tuple((n + stride - 1) // stride
                     for n in (self.width, self.height, self.slices))

    def first_voxel_xyz_m(self):
        x, y, z = self.mean_xyz_um
        # Reproduces both original 4x/20x Channel origins in the supplied report.
        # World axes are [-stage X, -stage Z, +stage Y], at voxel centers.
        return tuple(v * 1e-6 for v in (
            -x + (self.width - 1) * self.pixel_um / 2,
            -z + (self.height - 1) * self.pixel_um / 2,
            y - (self.slices - 1) * self.pixel_um / 2))

    def native_affine(self, stride=1):
        self.dimensions_xyz(stride)
        matrix = np.eye(4)
        # Both supplied original Channels use six significant digits for
        # spacing, but full header precision to compute their first voxel.
        spacing = float(format(self.pixel_um * 1e-6, ".6g")) * stride
        matrix[:3, :3] = np.diag((-spacing, -spacing, spacing))
        matrix[:3, 3] = self.first_voxel_xyz_m()
        return matrix

    def output_bytes(self, stride=1):
        return math.prod(self.dimensions_xyz(stride)) * np.dtype(self.dtype).itemsize

    def report(self, stride=1):
        result = asdict(self)
        result.update({
            "plugin_version": VERSION,
            "coordinate_mapping_validated": False,
            "placement_status": "awaiting open reference or saved calibration",
            "world_axis_convention": "-stage X, -stage Z, +stage Y",
            "origin_convention": "MeanSample and (dimension-1)/2; voxel centers",
            "center_shift_treatment": "Recorded; not added to reconstructed volume position",
            "sampling_stride": stride,
            "output_dimensions_xyz": self.dimensions_xyz(stride),
            "model_output_spacing_m": abs(float(self.native_affine(stride)[0, 0])),
            "intended_first_voxel_xyz_m": self.first_voxel_xyz_m(),
            "source_files_modified": False,
        })
        return result


def decode_metadata(ole, name, file_bytes):
    """Validate stream layout and the specific geometry family seen in reports."""
    paths = {"/".join(p).casefold(): p for p in ole.listdir(streams=True, storages=False)}
    fingerprint = hashlib.sha256()

    def raw(key, optional=False):
        p = paths.get(key.casefold())
        if p is None:
            if optional:
                return None
            raise TXMError("Required metadata is missing: " + key)
        size = ole.get_size(p)
        if size > 16 * 1024 * 1024:
            raise TXMError("Unexpectedly large geometry field: " + key)
        with ole.openstream(p) as stream:
            data = stream.read()
        if len(data) != size:
            raise TXMError("Truncated metadata: " + key)
        fingerprint.update(key.encode("utf-8") + b"\0" + data)
        return data

    def scalar(key, fmt, optional=False):
        data = raw(key, optional)
        if data is None:
            return None
        if len(data) != struct.calcsize("<" + fmt):
            raise TXMError("Unexpected field encoding: " + key)
        value = struct.unpack("<" + fmt, data)[0]
        if isinstance(value, float) and not math.isfinite(value):
            raise TXMError("Non-finite metadata: " + key)
        return value

    w = scalar("ImageInfo/ImageWidth", "I")
    h = scalar("ImageInfo/ImageHeight", "I")
    n = scalar("ImageInfo/NoOfImages", "I")
    if min(w, h, n) < 1:
        raise TXMError("Invalid volume dimensions.")
    dtype = {5: "<u2", 10: "<f4"}.get(scalar("ImageInfo/DataType", "I"))
    if dtype is None:
        raise TXMError("This build supports uint16 and float32 reconstructions only.")
    pixel = scalar("ImageInfo/PixelSize", "f")
    if pixel <= 0:
        raise TXMError("PixelSize must be positive.")
    if scalar("ImageInfo/AcquisitionMode", "I") != 10:
        raise TXMError("This is not the supported processed reconstruction mode (10).")
    if scalar("ImageInfo/SampleStackOrientation", "i") != 1:
        raise TXMError("This sample-stack orientation has not been established.")
    if scalar("ReconSettings/ReconOperation", "i") != 1:
        raise TXMError("This reconstruction operation has not been established.")
    if scalar("ReconSettings/RotationAngle", "f") != 0:
        raise TXMError("Rotated reconstructions require a validated transform.")
    if scalar("ReconSettings/ReconBinning", "i") != 1:
        raise TXMError("Reconstruction binning other than 1 is not supported yet.")
    if scalar("ReconSettings/ForceCropRect", "B") != 0:
        raise TXMError("Explicitly cropped reconstructions require a validated transform.")
    for side in ("Bottom", "Left", "Right", "Top"):
        key = "ReconSettings/CropRectangle/Rectangle/" + side
        if scalar(key, "i") != 0:
            raise TXMError("Nonzero reconstruction crop coordinates are not supported yet.")
    means = tuple(scalar("AutoRecon/MeanSample" + a, "f") for a in "XYZ")
    for axis, value in zip("XYZ", means):
        for field in ("MeanSample" + axis, "Sample" + axis + "StitchPosition"):
            other = scalar("ReconInputTomoParams/" + field, "f", optional=True)
            if other is not None and not math.isclose(value, other, rel_tol=5e-7, abs_tol=pixel*1e-3):
                raise TXMError("Inconsistent stage coordinates: " + field)
    for axis, expected in (("Width", w), ("Height", h)):
        value = scalar("ReconInputTomoParams/Cropped" + axis, "i", optional=True)
        if value is not None and value != expected:
            raise TXMError("Reconstruction dimensions disagree with the image dimensions.")

    # Validate every recorded slice position against the observed affine model.
    positions = []
    for axis, center in zip("XYZ", means):
        data = raw("ImageInfo/" + axis + "Position")
        if len(data) != n * 4:
            raise TXMError("Expected one " + axis + " stage position per reconstructed slice.")
        arr = np.frombuffer(data, dtype="<f4").astype(np.float64)
        if not np.isfinite(arr).all():
            raise TXMError("Non-finite slice coordinates.")
        tolerance = max(pixel * 0.001, abs(center) * np.finfo(np.float32).eps * 4, 1e-6)
        expected = center - n * pixel / 2 + np.arange(n) * pixel if axis == "Y" else center
        if float(np.max(np.abs(arr - expected))) > tolerance:
            raise TXMError("Slice coordinates do not fit the supported stage model (" + axis + ").")
        positions.append(arr)
    center_shift = scalar("ReconSettings/CenterShift", "f")

    image_paths = {}
    for key, path in paths.items():
        match = re.fullmatch(r"imagedata(\d+)/image(\d+)", key)
        if match:
            directory, index = map(int, match.groups())
            if index < 1 or directory != (index - 1)//100 + 1 or index in image_paths:
                raise TXMError("Unexpected or duplicate image stream layout.")
            image_paths[index] = path
    if sorted(image_paths) != list(range(1, n + 1)):
        raise TXMError("Image streams are missing, extra, or not numbered consecutively.")
    plane_bytes = w * h * np.dtype(dtype).itemsize
    if plane_bytes * n > file_bytes:
        raise TXMError("Declared pixel data exceeds the source file size.")
    for path in image_paths.values():
        if ole.get_size(path) != plane_bytes:
            raise TXMError("An image plane has an unexpected byte count.")
    if getattr(ole, "parsing_issues", []):
        raise TXMError("The compound-file reader reported structural problems.")
    meta = Metadata(name, file_bytes, w, h, n, dtype, pixel, means,
                    float(positions[1][0]), center_shift, fingerprint.hexdigest())
    return meta, image_paths


class TXMFile:
    def __init__(self, path):
        self.path = Path(path)
        self.ole = None

    def __enter__(self):
        if self.path.suffix.lower() != ".txm":
            raise TXMError("Select a processed .txm file.")
        self.ole = olefile.OleFileIO(str(self.path), write_mode=False,
                                   raise_defects=olefile.DEFECT_INCORRECT)
        try:
            self.meta, self.images = decode_metadata(self.ole, self.path.name, self.path.stat().st_size)
        except BaseException:
            self.ole.close()
            raise
        return self

    def __exit__(self, *args):
        if self.ole is not None:
            self.ole.close()

    def planes(self, stride=1, progress=None):
        self.meta.dimensions_xyz(stride)
        indices = range(0, self.meta.slices, stride)
        for j, source_index in enumerate(indices):
            if progress:
                progress(j, len(indices))
            plane = self.plane(source_index)
            yield j, plane[::stride, ::stride]
        if progress:
            progress(len(indices), len(indices))

    def plane(self, index):
        if not 0 <= index < self.meta.slices:
            raise TXMError("Slice index out of range.")
        with self.ole.openstream(self.images[index + 1]) as stream:
            data = stream.read()
        expected = self.meta.width * self.meta.height * np.dtype(self.meta.dtype).itemsize
        if len(data) != expected:
            raise TXMError("Truncated image data at slice " + str(index + 1))
        return np.frombuffer(data, dtype=self.meta.dtype).reshape(self.meta.height, self.meta.width)
