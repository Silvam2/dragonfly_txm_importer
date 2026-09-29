"""Build dist/dragonfly_txm_importer.zip from this repository."""
from pathlib import Path
import zipfile


def build():
    root = Path(__file__).resolve().parent
    destination = root / "dist" / "dragonfly_txm_importer.zip"
    destination.parent.mkdir(exist_ok=True)
    entries = [(root / "__main__.py", "__main__.py"),
               (root / "docs" / "USER_GUIDE.md", "README.md"),
               (root / "TEST_RESULTS.txt", "TEST_RESULTS.txt")]
    for directory in ("ZeissTXMImporter", "tests"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                entries.append((path, path.relative_to(root).as_posix()))
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, name in entries:
            archive.write(path, name)
    print(destination)
    return destination


if __name__ == "__main__":
    build()
