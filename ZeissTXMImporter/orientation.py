"""Match stored pixels to a reference without guessing permutations or flips."""
import itertools
import numpy as np
from .core import TXMError


def raw_shape(meta):
    return (meta.slices, meta.height, meta.width)


def validate_orientation(value):
    try:
        perm, flips = tuple(value["permutation"]), tuple(value["flips"])
    except (KeyError, TypeError):
        raise TXMError("Invalid voxel orientation.")
    if sorted(perm) != [0, 1, 2] or len(flips) != 3 or any(type(v) is not bool for v in flips):
        raise TXMError("Invalid voxel orientation.")
    return perm, flips


def detect_orientation(source, reference_array, progress=None):
    """Find a unique candidate, then the importer verifies EVERY output voxel."""
    shape = raw_shape(source.meta)
    if reference_array.dtype != np.dtype(source.meta.dtype):
        raise TXMError("The open reference has a different pixel type from the TXM.")
    axes = [np.unique(np.linspace(0, n-1, min(n, 9)).astype(int)) for n in shape]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    values = []
    for index, z in enumerate(axes[0]):
        if progress:
            progress(index, len(axes[0]))
        plane = source.plane(int(z))
        values.extend(plane[np.ix_(axes[1], axes[2])].ravel())
    values = np.asarray(values, dtype=reference_array.dtype)
    matches = []
    for perm in itertools.permutations(range(3)):
        if tuple(shape[i] for i in perm) != reference_array.shape:
            continue
        for flips in itertools.product((False, True), repeat=3):
            coords = tuple((shape[axis]-1-grid[:, axis]) if flip else grid[:, axis]
                           for axis, flip in zip(perm, flips))
            if np.array_equal(values, reference_array[coords], equal_nan=True):
                matches.append({"permutation": list(perm), "flips": list(flips)})
    if len(matches) != 1:
        reason = "none match" if not matches else "%d are indistinguishable" % len(matches)
        raise TXMError("Could not identify a unique pixel orientation (%s). The reference must be the same "
                       "unmodified, full-resolution TXM with no intensity conversion." % reason)
    return matches[0], len(values)


def oriented_planes(source, orientation, stride, progress=None):
    """Yield destination selector and plane in the reference's array order."""
    source.meta.dimensions_xyz(stride)
    perm, flips = validate_orientation(orientation)
    steps = [stride] * 3
    for dest_axis, raw_axis in enumerate(perm):
        if flips[dest_axis]:
            steps[raw_axis] = -stride
    shape = raw_shape(source.meta)
    slices = range(shape[0])[::steps[0]]
    fixed_axis = perm.index(0)
    remaining = tuple(axis-1 for axis in perm if axis != 0)
    for dest_index, source_index in enumerate(slices):
        if progress:
            progress(dest_index, len(slices))
        plane = source.plane(source_index)[::steps[1], ::steps[2]].transpose(remaining)
        selector = [slice(None)] * 3
        selector[fixed_axis] = dest_index
        yield tuple(selector), plane
    if progress:
        progress(len(slices), len(slices))
