"""Dragonfly bridge with reference pixel checks and explicit affine readback."""
import json
import unicodedata
import numpy as np
from .core import TXMFile, TXMError
from .orientation import detect_orientation, oriented_planes, raw_shape, validate_orientation
from .calibration import usable


def vector(components):
    from ORSModel import Vector3
    value = Vector3()
    value.setXYZ(*map(float, components))
    return value


def xyz(value):
    return np.array((value.getX(), value.getY(), value.getZ()), dtype=float)


def world_affine(channel):
    origin = xyz(channel.getVoxelToWorldCoordinates(vector((0, 0, 0))))
    matrix = np.eye(4)
    matrix[:3, 3] = origin
    for index in range(3):
        basis = [0, 0, 0]
        basis[index] = 1
        matrix[:3, index] = xyz(channel.getVoxelToWorldCoordinates(vector(basis))) - origin
    return matrix


def affine_error_m(actual, intended, dimensions_xyz):
    # Compare the whole field of view, not just its origin or a one-voxel step.
    corners = np.array([[x, y, z, 1.] for x in (0, dimensions_xyz[0]-1)
                        for y in (0, dimensions_xyz[1]-1) for z in (0, dimensions_xyz[2]-1)])
    return float(np.max(np.linalg.norm((corners @ (actual-intended).T)[:, :3], axis=1)))


def set_affine(channel, intended, dimensions_xyz):
    basis = intended[:3, :3]
    spacing = np.linalg.norm(basis, axis=0)
    if not np.isfinite(intended).all() or np.any(spacing <= 0):
        raise TXMError("Invalid target geometry.")
    directions = basis / spacing
    if not np.allclose(directions.T @ directions, np.eye(3), atol=1e-7):
        raise TXMError("Sheared reference geometries are not supported.")
    if not np.isclose(np.linalg.det(directions), 1., atol=1e-7):
        raise TXMError("The reference must have a right-handed voxel basis.")
    box = channel.getBox()
    for axis in range(3):
        getattr(box, "setDirection%d" % axis)(vector(directions[:, axis]))
    channel.setBox(box)
    for axis, name in enumerate("XYZ"):
        getattr(channel, "set" + name + "Spacing")(float(spacing[axis]))
    current = world_affine(channel)
    channel.setOrigin(vector(xyz(channel.getOrigin()) + intended[:3, 3] - current[:3, 3]))
    actual = world_affine(channel)
    error = affine_error_m(actual, intended, dimensions_xyz)
    if error > 1e-10:
        raise TXMError("Dragonfly geometry readback differs from the requested transform (%.6g m)." % error)
    return actual, error


class ReferenceChoiceRequired(TXMError):
    def __init__(self, channels):
        super().__init__("Several open volumes fit the full-resolution dimensions. Select the correct original; its pixels will be checked.")
        self.channels = channels


def importer_metadata(channel):
    """A nonempty missing-value placeholder is not proof of plugin provenance."""
    try:
        value = channel.getUserInfo("ZeissTXMImporter")
    except KeyError:
        return None, "no importer metadata"
    if value is None or isinstance(value, str) and not value.strip():
        return None, "no importer metadata"
    try:
        parsed = value if isinstance(value, dict) else json.loads(value)
    except (ValueError, TypeError):
        return None, "unrecognized metadata response; not a plugin tag"
    if (isinstance(parsed, dict) and isinstance(parsed.get("plugin_version"), str)
            and isinstance(parsed.get("geometry_header_sha256"), str)):
        return parsed, "plugin output " + parsed["plugin_version"]
    return None, "no valid plugin tag"


def normalized_title(title):
    value = unicodedata.normalize("NFKC", str(title)).strip().replace("\\", "/").rsplit("/", 1)[-1]
    if value.casefold().endswith(".txm"):
        value = value[:-4]
    return value.strip().casefold()


def inspect_references(meta=None, channels=None):
    """Return candidate objects separately from JSON-serializable diagnostics."""
    from ORSModel import Channel
    if channels is None:
        channels = Channel.getAllInstances()
    candidates, rows = [], []
    for index, channel in enumerate(channels):
        row = {"index": index + 1, "title": "<unavailable>", "eligible": False, "reasons": []}
        try:
            row["title"] = channel.getTitle()
            dims = [channel.getXSize(), channel.getYSize(), channel.getZSize(), channel.getTSize()]
            row["dimensions_xyzt"] = dims
            marker, status = importer_metadata(channel)
            row["metadata_status"] = status
            row["name_matches"] = meta is not None and normalized_title(row["title"]) == normalized_title(meta.name)
            if marker is not None:
                row["reasons"].append("created by this plugin")
            if dims[3] != 1:
                row["reasons"].append("requires one time point")
            if meta is not None and sorted(dims[:3]) != sorted(raw_shape(meta)):
                row["reasons"].append("dimensions do not match the full-resolution TXM")
            row["eligible"] = not row["reasons"]
            if row["eligible"]:
                candidates.append((channel, row))
        except Exception as error:
            row["reasons"].append("cannot inspect volume: " + str(error))
        rows.append(row)
    return candidates, rows


def find_reference(meta, channels=None):
    candidates, _ = inspect_references(meta, channels)
    named = [(channel, row) for channel, row in candidates if row["name_matches"]]
    choices = named if named else candidates
    if len(choices) > 1:
        raise ReferenceChoiceRequired([channel for channel, _ in choices])
    # A unique dimension match is only a candidate. import_txm still verifies
    # pixel orientation and every output voxel before publishing anything.
    return choices[0][0] if choices else None


def reference_failure_message(meta, rows=None):
    if rows is None:
        _, rows = inspect_references(meta)
    expected = " x ".join(map(str, (meta.width, meta.height, meta.slices)))
    message = ("No eligible open reference for %s (full size %s). Adding a file to this plugin only queues it. "
               "Load the original volume through Dragonfly's normal Open/Import command first, then retry. "
               "Open volumes: " % (meta.name, expected))
    if not rows:
        return message + "NONE."
    details = []
    for row in rows[:12]:
        dims = " x ".join(map(str, row.get("dimensions_xyzt", [])[:3]))
        reason = "; ".join(row["reasons"]) or "eligible candidate"
        details.append("%s [%s]: %s" % (row["title"], dims, reason))
    return message + " | ".join(details) + (" | More volumes listed in the placement report." if len(rows) > 12 else "")


def import_txm(path, stride=4, progress=None, expected_header=None, reference=None, profile=None):
    from ORSModel import Channel
    channel = None
    with TXMFile(path) as source:
        meta = source.meta
        meta.dimensions_xyz(stride)
        if expected_header is not None and meta.geometry_header_sha256 != expected_header:
            raise TXMError("The source metadata changed after selection. Add the file again.")
        report = meta.report(stride)
        if reference is not None:
            ref_array = reference.getNDArray(0)
            orientation, probe_count = detect_orientation(source, ref_array, progress)
            intended = world_affine(reference)
            report["reference_channel"] = channel_report(reference)
            report["orientation_probe_count"] = probe_count
            reference_dims = tuple(reversed(ref_array.shape))
            model_error = affine_error_m(intended, meta.native_affine(), reference_dims)
            report["native_model_error_m"] = model_error
            report["native_model_matches"] = (model_error <= 1e-10 and
                not bool(reference.getSpaceHasBeenTransformed()) and orientation["permutation"] == [0, 1, 2])
            intended[:3, :3] *= stride
            ref_sampled = ref_array[::stride, ::stride, ::stride]
        elif usable(profile):
            orientation = {k: profile[k] for k in ("permutation", "flips")}
            intended = meta.native_affine(stride)
            report["calibration_references"] = profile["references"]
            report["native_model_matches"] = None
        else:
            raise TXMError(reference_failure_message(meta))
        perm, _ = validate_orientation(orientation)
        shape = tuple((raw_shape(meta)[i]+stride-1)//stride for i in perm)
        dims = shape[::-1]
        try:
            channel = Channel()
            channel.setXYZTSize(*dims, 1)
            initialized = (channel.initializeDataForUSHORT() if meta.dtype == "<u2"
                           else channel.initializeDataForFLOAT())
            if not initialized:
                raise MemoryError("Dragonfly could not allocate the volume. Try a smaller preview.")
            target = channel.getNDArray(0)
            if tuple(target.shape) != shape or target.dtype != np.dtype(meta.dtype) or not target.flags.writeable:
                raise TXMError("Unexpected Dragonfly array shape, type, or write permission.")
            for selector, plane in oriented_planes(source, orientation, stride, progress):
                if reference is not None and not np.array_equal(plane, ref_sampled[selector], equal_nan=True):
                    raise TXMError("Pixel verification failed. The original does not match this TXM throughout "
                                   "the selected sampling grid. No new volume was published.")
                target[selector] = plane
            voxel_count = int(target.size)
            del target
            actual, error = set_affine(channel, intended, dims)
            channel.setCurrentShapeAsOriginal()
            checked = reference is not None
            suffix = "" if stride == 1 else " preview 1/" + str(stride)
            channel.setTitle(meta.name + suffix + (" [reference checked]" if checked else " [calibrated placement]"))
            report.update({
                "coordinate_mapping_validated": checked,
                "validation_scope": "every imported voxel and world geometry compared with the open reference" if checked
                    else "saved convention from checked references; this file has no independent reference",
                "placement_status": "reference checked" if checked else "calibrated convention",
                "voxel_orientation": orientation,
                "reference_voxels_verified": checked,
                "verified_voxel_count": voxel_count if checked else 0,
                "output_dimensions_xyz": dims,
                "actual_voxel_to_world_m": actual.tolist(),
                "target_voxel_to_world_m": intended.tolist(),
                "geometry_readback_max_corner_error_m": error,
            })
            channel.setUserInfo("ZeissTXMImporter", json.dumps(report))
            channel.setDataDirty()
            channel.publish()
            return channel, report
        except BaseException:
            if "target" in locals():
                del target
            if channel is not None:
                channel.deleteObject()
            raise


def channel_report(channel):
    result = {
        "title": channel.getTitle(),
        "dimensions_xyzt": [channel.getXSize(), channel.getYSize(), channel.getZSize(), channel.getTSize()],
        "spacing_m": [channel.getXSpacing(), channel.getYSpacing(), channel.getZSpacing()],
        "voxel_to_world_m": world_affine(channel).tolist(),
    }
    for method, key in (("getSpaceHasBeenTransformed", "has_been_transformed"), ("getGUID", "guid")):
        if hasattr(channel, method):
            result[key] = getattr(channel, method)()
    marker, status = importer_metadata(channel)
    result["importer_metadata_status"] = status
    if marker is not None:
        result["txm_import"] = marker
    return result
