"""Run: python -m unittest discover -s tests -v (requires NumPy).

ORS is deliberately replaced with an explicit mock. These tests cannot establish
native ZEISS geometry compatibility or Windows GUI/runtime compatibility.
"""
from pathlib import Path
from contextlib import contextmanager
import base64
import importlib
import itertools
import io
import json
import os
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import numpy as np

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "ZeissTXMImporter"
namespace = types.ModuleType("txm_test_package")
namespace.__path__ = [str(PACKAGE_ROOT)]
sys.modules[namespace.__name__] = namespace
core = importlib.import_module("txm_test_package.core")
adapter = importlib.import_module("txm_test_package.adapter")
installer = importlib.import_module("txm_test_package.install")
orientation = importlib.import_module("txm_test_package.orientation")
calibration = importlib.import_module("txm_test_package.calibration")


def streams_for_volume(dtype="<u2", width=64, height=40, count=7, pixel=.5):
    streams = {}
    def put(key, value, fmt="i"):
        streams[key] = struct.pack("<" + fmt, value)
    for key, value in {"ImageWidth": width, "ImageHeight": height, "NoOfImages": count,
                       "DataType": 5 if dtype == "<u2" else 10,
                       "AcquisitionMode": 10, "SampleStackOrientation": 1}.items():
        put("ImageInfo/" + key, value)
    put("ImageInfo/PixelSize", pixel, "f")
    for axis, value in zip("XYZ", (10., -20., 30.)):
        put("AutoRecon/MeanSample" + axis, value, "f")
        positions = value - count*pixel/2 + np.arange(count)*pixel if axis == "Y" else np.full(count, value)
        streams["ImageInfo/" + axis + "Position"] = positions.astype("<f4").tobytes()
    for key, value, fmt in (("ReconOperation", 1, "i"), ("ReconBinning", 1, "i"),
                            ("RotationAngle", 0., "f"), ("CenterShift", 12.25, "f"),
                            ("ForceCropRect", 0, "B")):
        put("ReconSettings/" + key, value, fmt)
    for side in ("Bottom", "Left", "Top", "Right"):
        put("ReconSettings/CropRectangle/Rectangle/" + side, 0)
    data = np.arange(count*height*width).reshape(count, height, width).astype(dtype)
    if dtype == "<f4":
        data = data/np.float32(7) - np.float32(100)
    for index, plane in enumerate(data):
        streams["ImageData%d/Image%d" % (index//100+1, index+1)] = plane.tobytes()
    return streams, data


def write_cfb(path, streams):
    """Small independent CFB v3 fixture writer, including FAT and MiniFAT."""
    FREE, END, FAT = 0xffffffff, 0xfffffffe, 0xfffffffd
    nodes = {"": {"name": "Root Entry", "type": 5}}
    for key, data in streams.items():
        parts = key.split("/")
        for index in range(1, len(parts)):
            prefix = "/".join(parts[:index])
            nodes.setdefault(prefix, {"name": parts[index-1], "type": 1})
        nodes[key] = {"name": parts[-1], "type": 2, "data": data}
    keys = list(nodes)
    for index, key in enumerate(keys):
        nodes[key].update(index=index, left=FREE, right=FREE, child=FREE, start=END, size=0)
    for key, node in nodes.items():
        if node["type"] == 2:
            continue
        children = [k for k in keys if k and k.rpartition("/")[0] == key]
        children.sort(key=lambda k: (len(nodes[k]["name"]), nodes[k]["name"].upper()))
        def tree(items):
            if not items:
                return FREE
            mid = len(items)//2
            child = nodes[items[mid]]
            child["left"] = tree(items[:mid])
            child["right"] = tree(items[mid+1:])
            return child["index"]
        node["child"] = tree(children)
    blocks, links = [], []
    def allocate(data):
        if not data:
            return END
        first = len(blocks)
        for offset in range(0, len(data), 512):
            blocks.append(data[offset:offset+512].ljust(512, b"\0"))
            links.append(len(blocks))
        links[-1] = END
        return first
    mini, mini_links = bytearray(), []
    for key, node in nodes.items():
        if node["type"] != 2:
            continue
        data = node["data"]
        node["size"] = len(data)
        if len(data) >= 4096:
            node["start"] = allocate(data)
        else:
            node["start"] = len(mini_links)
            for offset in range(0, len(data), 64):
                mini.extend(data[offset:offset+64].ljust(64, b"\0"))
                mini_links.append(len(mini_links)+1)
            mini_links[-1] = END
    nodes[""].update(start=allocate(mini), size=len(mini))
    mini_fat_data = struct.pack("<%dI" % len(mini_links), *mini_links)
    mini_fat_data += b"\xff" * ((-len(mini_fat_data)) % 512)
    mini_fat_start = allocate(mini_fat_data)
    directory = bytearray()
    for node in nodes.values():
        entry = bytearray(128)
        name = (node["name"] + "\0").encode("utf-16le")
        if len(name) > 64:
            raise ValueError("Fixture entry name too long")
        entry[:len(name)] = name
        struct.pack_into("<HBBIII", entry, 64, len(name), node["type"], 1,
                         node["left"], node["right"], node["child"])
        struct.pack_into("<IQ", entry, 116, node["start"], node["size"])
        directory.extend(entry)
    directory_start = allocate(directory)
    fat_count = 1
    while (len(blocks) + fat_count + 127)//128 != fat_count:
        fat_count = (len(blocks)+fat_count+127)//128
    if fat_count > 109:
        raise ValueError("Fixture too large")
    fat_ids = list(range(len(blocks), len(blocks)+fat_count))
    fat_links = links + [FAT]*fat_count
    fat_links += [FREE]*(128*fat_count-len(fat_links))
    fat_data = struct.pack("<%dI" % len(fat_links), *fat_links)
    blocks.extend(fat_data[i:i+512] for i in range(0, len(fat_data), 512))
    header = bytearray(512)
    header[:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", header, 24, 0x3e, 3, 0xfffe, 9, 6)
    struct.pack_into("<IIIIIIIII", header, 40, 0, fat_count, directory_start,
                     0, 4096, mini_fat_start, len(mini_fat_data)//512, END, 0)
    struct.pack_into("<109I", header, 76, *(fat_ids+[FREE]*(109-len(fat_ids))))
    Path(path).write_bytes(header+b"".join(blocks))


class V:
    def __init__(self): self.a = np.zeros(3)
    def setXYZ(self, *a): self.a = np.array(a, dtype=float)
    def getX(self): return float(self.a[0])
    def getY(self): return float(self.a[1])
    def getZ(self): return float(self.a[2])


class MockChannel:
    created = []
    origin_offset = .5
    def __init__(self):
        self.created.append(self)
        self.origin = np.array((1., 2., 3.))
        self.spacing = np.ones(3)
        self.directions = np.eye(3)
        self.deleted = self.published = False
        self.info = {}
    def setXYZTSize(self, x, y, z, t): self.dims = (x, y, z, t)
    def setXSpacing(self, p): self.spacing[0] = p
    def setYSpacing(self, p): self.spacing[1] = p
    def setZSpacing(self, p): self.spacing[2] = p
    def initializeDataForUSHORT(self):
        self.data = np.empty(self.dims[:3][::-1], dtype="<u2")
        return True
    def initializeDataForFLOAT(self):
        self.data = np.empty(self.dims[:3][::-1], dtype="<f4")
        return True
    def getNDArray(self, t): return self.data
    def getOrigin(self):
        value = V(); value.a = self.origin.copy(); return value
    def setOrigin(self, value): self.origin = value.a.copy()
    def getVoxelToWorldCoordinates(self, value):
        result = V(); result.a = self.origin + self.directions @ ((value.a+self.origin_offset)*self.spacing); return result
    def getBox(self):
        class Box:
            def __init__(self, directions): self.directions = directions.copy()
            def setDirection0(self, v): self.directions[:, 0] = v.a
            def setDirection1(self, v): self.directions[:, 1] = v.a
            def setDirection2(self, v): self.directions[:, 2] = v.a
        return Box(self.directions)
    def setBox(self, box): self.directions = box.directions.copy()
    def setCurrentShapeAsOriginal(self): self.original = self.origin.copy()
    def setTitle(self, title): self.title = title
    def setUserInfo(self, key, value): self.info[key] = value
    def setDataDirty(self): self.dirty = True
    def publish(self): self.published = True
    def deleteObject(self): self.deleted = True
    def getTitle(self): return getattr(self, "title", "")
    def getXSize(self): return self.dims[0]
    def getYSize(self): return self.dims[1]
    def getZSize(self): return self.dims[2]
    def getTSize(self): return self.dims[3]
    def getXSpacing(self): return float(self.spacing[0])
    def getYSpacing(self): return float(self.spacing[1])
    def getZSpacing(self): return float(self.spacing[2])
    def getUserInfo(self, key): return self.info.get(key, "")
    def getSpaceHasBeenTransformed(self): return False
    @classmethod
    def getAllInstances(cls): return [c for c in cls.created if not c.deleted]


class MemoryOle:
    def __init__(self, data, sizes=None): self.data, self.sizes = data, sizes or {}
    def listdir(self, **kw): return [key.split("/") for key in list(self.data)+list(self.sizes)]
    def get_size(self, path):
        key = "/".join(path)
        return self.sizes[key] if key in self.sizes else len(self.data[key])
    def openstream(self, path): return io.BytesIO(self.data["/".join(path)])


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "fixture.txm"
        self.streams, self.data = streams_for_volume()
        write_cfb(self.path, self.streams)
        self.ors = types.ModuleType("ORSModel")
        self.ors.Channel, self.ors.Vector3 = MockChannel, V
        self.patcher = patch.dict(sys.modules, {"ORSModel": self.ors})
        self.patcher.start()
        MockChannel.created.clear()
        self.profile = {"permutation": [0, 1, 2], "flips": [False]*3,
                        "references": [{"geometry_header_sha256": str(i), "pixel_um": float(i),
                                        "native_model_matches": True, "verified_voxel_count": 1}
                                       for i in (1, 2)]}

    def import_volume(self, *args, **kwargs):
        kwargs.setdefault("profile", self.profile)
        return adapter.import_txm(*args, **kwargs)

    def reference(self, array=None):
        with core.TXMFile(self.path) as source:
            meta = source.meta
        ref = MockChannel()
        ref.data = (self.data if array is None else array).copy()
        ref.dims = (*ref.data.shape[::-1], 1)
        ref.setTitle(meta.name[:-4])
        adapter.set_affine(ref, meta.native_affine(), ref.dims[:3])
        return ref

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_real_ole_uint16_and_axis_mapping(self):
        channel, report = self.import_volume(self.path, 1)
        np.testing.assert_array_equal(channel.data, self.data)
        np.testing.assert_allclose(adapter.world_affine(channel)[:3, 3], [5.75e-6, -20.25e-6, -21.5e-6], rtol=0, atol=1e-14)
        self.assertTrue(channel.published)
        self.assertFalse(channel.deleted)
        self.assertFalse(report["coordinate_mapping_validated"])
        self.assertEqual(report["center_shift"], 12.25)  # Not added to position.

    def test_preview_keeps_first_voxel_and_strides_all_axes(self):
        full, _ = self.import_volume(self.path, 1)
        preview, _ = self.import_volume(self.path, 4)
        np.testing.assert_array_equal(preview.data, full.data[::4, ::4, ::4])
        np.testing.assert_allclose(adapter.world_affine(preview)[:3, 3], adapter.world_affine(full)[:3, 3], atol=1e-14)
        np.testing.assert_allclose(adapter.world_affine(preview)[:3, :3], np.diag([-2e-6, -2e-6, 2e-6]), atol=1e-14)
        self.assertEqual(preview.dims, (16, 10, 2, 1))

    def test_float32_preserves_values(self):
        streams, data = streams_for_volume("<f4")
        write_cfb(self.path, streams)
        channel, _ = self.import_volume(self.path, 1)
        np.testing.assert_array_equal(channel.data, data)

    def test_origin_convention_does_not_change_target_coordinates(self):
        for offset in (0, .5):
            with patch.object(MockChannel, "origin_offset", offset):
                channel, _ = self.import_volume(self.path, 2)
                np.testing.assert_allclose(adapter.world_affine(channel)[:3, 3], [5.75e-6, -20.25e-6, -21.5e-6], atol=1e-14)

    def test_cancel_deletes_unpublished_channel(self):
        def cancel(done, total):
            if done == 2: raise core.Cancelled()
        with self.assertRaises(core.Cancelled): self.import_volume(self.path, 1, cancel)
        self.assertTrue(MockChannel.created[-1].deleted)
        self.assertFalse(MockChannel.created[-1].published)

    def test_unsupported_geometry_and_corrupt_layout_rejected(self):
        changes = [
            ("ReconSettings/RotationAngle", struct.pack("<f", 30)),
            ("ReconSettings/ForceCropRect", b"\1"),
            ("ImageInfo/SampleStackOrientation", struct.pack("<i", 2)),
            ("ImageInfo/PixelSize", struct.pack("<f", float("nan"))),
            ("ImageInfo/YPosition", np.zeros(7, dtype="<f4").tobytes()),
            ("ImageData1/Image2", b"\0"*1024),
            ("ReconSettings/CropRectangle/Rectangle/Top", struct.pack("<i", 1)),
        ]
        for field, value in changes:
            with self.subTest(field=field):
                streams = dict(self.streams); streams[field] = value
                write_cfb(self.path, streams)
                with self.assertRaises(core.TXMError):
                    with core.TXMFile(self.path): pass
        streams = dict(self.streams); del streams["ImageData1/Image2"]
        write_cfb(self.path, streams)
        with self.assertRaises(core.TXMError):
            with core.TXMFile(self.path): pass

    def test_source_is_unchanged(self):
        original = self.path.read_bytes()
        self.import_volume(self.path, 4)
        self.assertEqual(original, self.path.read_bytes())

    def test_changed_metadata_rejected_before_allocation(self):
        with self.assertRaises(core.TXMError): adapter.import_txm(self.path, 4, expected_header="invalid")
        self.assertFalse(MockChannel.created)

    def test_relative_stage_translation(self):
        first, _ = self.import_volume(self.path, 2)
        streams = dict(self.streams)
        streams["AutoRecon/MeanSampleX"] = struct.pack("<f", 110.)
        streams["ImageInfo/XPosition"] = np.full(7, 110., dtype="<f4").tobytes()
        write_cfb(self.path, streams)
        second, _ = self.import_volume(self.path, 2)
        np.testing.assert_allclose(adapter.world_affine(second)[:3, 3]-adapter.world_affine(first)[:3, 3], [-100e-6, 0, 0], atol=1e-14)

    def test_reference_detects_all_axis_permutations_and_flips(self):
        with core.TXMFile(self.path) as source:
            for perm in itertools.permutations(range(3)):
                for flips in itertools.product((False, True), repeat=3):
                    expected = self.data.transpose(perm)[tuple(slice(None, None, -1 if v else 1) for v in flips)]
                    detected, _ = orientation.detect_orientation(source, expected)
                    self.assertEqual(detected, {"permutation": list(perm), "flips": list(flips)})
                    output = np.empty(expected[::4, ::4, ::4].shape, dtype=expected.dtype)
                    for selector, plane in orientation.oriented_planes(source, detected, 4):
                        output[selector] = plane
                    np.testing.assert_array_equal(output, expected[::4, ::4, ::4])

    def test_reference_pixel_and_geometry_match(self):
        ref = self.reference(self.data[:, ::-1, :])
        original = ref.data.copy()
        channel, report = self.import_volume(self.path, 4, reference=ref)
        np.testing.assert_array_equal(channel.data, ref.data[::4, ::4, ::4])
        np.testing.assert_array_equal(ref.data, original)
        intended = adapter.world_affine(ref); intended[:3, :3] *= 4
        self.assertLess(adapter.affine_error_m(adapter.world_affine(channel), intended, channel.dims[:3]), 1e-10)
        self.assertTrue(report["coordinate_mapping_validated"])
        self.assertTrue(report["native_model_matches"])
        self.assertEqual(report["verified_voxel_count"], channel.data.size)
        self.assertEqual(report["voxel_orientation"]["flips"], [False, True, False])

    def test_mismatch_between_probe_points_aborts_publication(self):
        ref = self.reference()
        ref.data[3, 11, 11] += 1
        with self.assertRaisesRegex(core.TXMError, "Pixel verification failed"):
            self.import_volume(self.path, 1, reference=ref)
        self.assertTrue(MockChannel.created[-1].deleted)
        self.assertFalse(MockChannel.created[-1].published)

    def test_ambiguous_pixel_orientation_rejected(self):
        streams, data = streams_for_volume()
        for key in streams:
            if key.startswith("ImageData"):
                streams[key] = bytes(len(streams[key]))
        write_cfb(self.path, streams)
        ref = self.reference(np.zeros_like(data))
        with self.assertRaisesRegex(core.TXMError, "unique pixel orientation"):
            self.import_volume(self.path, 4, reference=ref)

    def test_missing_reference_and_calibration_do_not_guess(self):
        with self.assertRaisesRegex(core.TXMError, "No matching original"):
            adapter.import_txm(self.path, 4)
        self.assertFalse(MockChannel.created)

    def test_reference_selection_excludes_plugin_and_ambiguous_originals(self):
        ref = self.reference()
        with core.TXMFile(self.path) as source:
            self.assertIs(adapter.find_reference(source.meta), ref)
            another = self.reference()
            another.setUserInfo("ZeissTXMImporter", "{}")
            self.assertIs(adapter.find_reference(source.meta), ref)
            another.info.clear()
            with self.assertRaises(core.TXMError): adapter.find_reference(source.meta)

    def test_two_distinct_reference_checks_enable_calibration(self):
        path = Path(self.tmp.name)/"calibration.json"
        for index, pixel in enumerate((.5, .25)):
            streams, self.data = streams_for_volume(pixel=pixel)
            write_cfb(self.path, streams)
            ref = self.reference(self.data[:, ::-1, :])
            _, report = self.import_volume(self.path, 4, reference=ref)
            self.assertEqual(calibration.record(report, path), index == 1)
        with core.TXMFile(self.path) as source:
            profile = calibration.get_profile(source.meta, path)
        self.assertIsNotNone(profile)
        channel, standalone = adapter.import_txm(self.path, 4, profile=profile)
        np.testing.assert_array_equal(channel.data, self.data[:, ::-1, :][::4, ::4, ::4])
        self.assertFalse(standalone["coordinate_mapping_validated"])
        report["voxel_orientation"]["flips"] = [True, False, False]
        self.assertFalse(calibration.record(report, path))

    def test_supplied_native_origins_and_full_affines(self):
        path = os.environ.get("TXM_PLACEMENT_REPORT")
        if not path:
            self.skipTest("Set TXM_PLACEMENT_REPORT to the supplied placement report.")
        report = json.loads(Path(path).read_text())
        for item in report["selected_files"]:
            meta = core.Metadata(**{k: item[k] for k in core.Metadata.__dataclass_fields__})
            ref = next(c for c in report["open_channels"] if c["title"] == meta.name[:-4])
            matrix = np.array(ref["voxel_to_world_m"])
            self.assertLess(adapter.affine_error_m(matrix, meta.native_affine(), meta.dimensions_xyz()), 1e-12)

    def test_install_and_backup(self):
        target = Path(self.tmp.name)/"pythonUserExtensions"/"Plugins"
        installed, backup = installer.install_to(target)
        self.assertIsNone(backup)
        self.assertTrue((Path(installed)/"core.py").is_file())
        marker = Path(installed)/"test-marker.txt"; marker.write_text("original")
        installed, backup = installer.install_to(target)
        self.assertFalse(marker.exists())
        self.assertEqual((Path(backup)/"test-marker.txt").read_text(), "original")
        self.assertNotIn("Plugins", Path(backup).relative_to(target.parent).parts)

    def test_supplied_header_reports_when_available(self):
        folder = os.environ.get("TXM_HEADER_REPORT_DIR")
        if not folder:
            self.skipTest("Set TXM_HEADER_REPORT_DIR to the supplied report directory.")
        paths = sorted(Path(folder).glob("*txm_headers*.json"))
        self.assertEqual(len(paths), 3)
        for path in paths:
            entry = json.loads(path.read_text())["files"][0]
            data = {k: base64.b64decode(v["raw_base64"]) for k, v in entry["geometry_headers"].items() if "raw_base64" in v}
            summary = entry["summary"]
            sizes = {"ImageData%d/Image%d" % (i//100+1, i+1): summary["width"]*summary["height"]*2 for i in range(summary["slice_count"])}
            meta, _ = core.decode_metadata(MemoryOle(data, sizes), entry["name"], entry["size_bytes"])
            self.assertEqual(meta.width, summary["width"])
            self.assertEqual(meta.slices, summary["slice_count"])
            self.assertEqual(meta.pixel_um, summary["voxel_size_um"])


if __name__ == "__main__":
    unittest.main()
