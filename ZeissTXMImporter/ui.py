from datetime import datetime, timezone
from pathlib import Path
import json
import platform
import traceback

from PyQt6 import QtCore, QtWidgets
from .core import TXMFile, Cancelled, VERSION
from .adapter import (import_txm, channel_report, find_reference, inspect_references,
                      ReferenceChoiceRequired)
from . import calibration

_windows = []


class ImportPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.import_results = []
        self.busy = False
        layout = QtWidgets.QVBoxLayout(self)
        notice = QtWidgets.QLabel(
            "Adding .txm files here queues them; it does not open the original reference volumes. "
            "For the first calibration, load the full-resolution originals in Dragonfly's main object list. "
            "Use Show open volumes to check what this plugin can see. Renamed originals are supported.")
        notice.setWordWrap(True)
        notice.setStyleSheet("padding: 10px; background-color: #664800; color: white;")
        layout.addWidget(notice)
        description = QtWidgets.QLabel("Start with a 1/4 preview. Full resolution retains the stored voxel values. "
                                      "Preview samples every nth voxel without interpolation.")
        description.setWordWrap(True)
        layout.addWidget(description)
        row = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("Add .txm files...")
        self.clear_button = QtWidgets.QPushButton("Clear list")
        self.references_button = QtWidgets.QPushButton("Show open volumes")
        self.sampling = QtWidgets.QComboBox()
        for text, stride in (("1/4 preview", 4), ("1/8 preview", 8), ("1/2 preview", 2), ("Full resolution", 1)):
            self.sampling.addItem(text, stride)
        row.addWidget(self.add_button)
        row.addWidget(self.clear_button)
        row.addWidget(self.references_button)
        row.addStretch()
        row.addWidget(QtWidgets.QLabel("Resolution:"))
        row.addWidget(self.sampling)
        layout.addLayout(row)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Source file", "Output X × Y × Z", "Voxel (µm)", "Stage center X, Y, Z (µm)", "Pixels (MiB)"])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)
        self.total = QtWidgets.QLabel("No files selected.")
        layout.addWidget(self.total)
        row = QtWidgets.QHBoxLayout()
        self.import_button = QtWidgets.QPushButton("Import and check references")
        self.save_button = QtWidgets.QPushButton("Save placement report...")
        self.install_button = QtWidgets.QPushButton("Install File menu entry")
        row.addWidget(self.import_button)
        row.addWidget(self.save_button)
        row.addStretch()
        row.addWidget(self.install_button)
        layout.addLayout(row)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(145)
        layout.addWidget(self.log)
        self.add_button.clicked.connect(self.add_files)
        self.clear_button.clicked.connect(self.clear_files)
        self.references_button.clicked.connect(self.show_open_volumes)
        self.sampling.currentIndexChanged.connect(self.refresh)
        self.import_button.clicked.connect(self.import_files)
        self.save_button.clicked.connect(self.save_report)
        self.install_button.clicked.connect(self.install)
        self.refresh()
        self.show_open_volumes()

    def append(self, message):
        self.log.appendPlainText(message)

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.add_button, self.clear_button, self.references_button, self.sampling,
                       self.import_button, self.save_button, self.install_button):
            widget.setEnabled(not busy)
        if not busy:
            self.refresh()

    def refresh(self, *_):
        stride = int(self.sampling.currentData())
        self.table.setRowCount(len(self.entries))
        total = 0
        for row, (_, meta) in enumerate(self.entries):
            total += meta.output_bytes(stride)
            values = [meta.name, " × ".join(map(str, meta.dimensions_xyz(stride))),
                      "%.9g" % (meta.pixel_um*stride),
                      ", ".join("%.9g" % v for v in meta.mean_xyz_um),
                      "%.1f" % (meta.output_bytes(stride)/2**20)]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
        self.total.setText("%d file(s), %.1f MiB of voxel data, plus Dragonfly display overhead." %
                           (len(self.entries), total/2**20))
        self.import_button.setEnabled(bool(self.entries) and not self.busy)
        self.import_button.setText("Import full volumes" if stride == 1 else "Import previews")

    def add_files(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select processed ZEISS reconstructions", "", "ZEISS reconstructions (*.txm *.TXM)")
        if not paths:
            return
        self.set_busy(True)
        try:
            existing = {str(Path(p).resolve()).casefold() for p, _ in self.entries}
            for path in paths:
                if str(Path(path).resolve()).casefold() in existing:
                    continue
                try:
                    with TXMFile(path) as source:
                        self.entries.append((path, source.meta))
                    existing.add(str(Path(path).resolve()).casefold())
                    self.append("Headers checked: " + Path(path).name)
                    self.log_reference_status(source.meta)
                except Exception as error:
                    self.append("Cannot add " + Path(path).name + ": " + str(error))
        finally:
            self.set_busy(False)

    def clear_files(self):
        self.entries.clear()
        self.refresh()

    def log_reference_status(self, meta):
        try:
            reference = find_reference(meta)
            if reference is not None:
                self.append("Reference candidate: " + reference.getTitle() + ". Pixels will be checked during import.")
            elif calibration.get_profile(meta) is not None:
                self.append("Saved calibration is available for this file type.")
            else:
                self.append("No eligible reference is open for " + meta.name + ". Click Show open volumes.")
        except ReferenceChoiceRequired as choice:
            self.append("%d reference candidates for %s. You will be asked to select one." % (len(choice.channels), meta.name))
        except Exception as error:
            self.append("Reference check: " + str(error))

    def show_open_volumes(self):
        try:
            _, rows = inspect_references()
            self.append("Open volumes visible to the plugin: " + str(len(rows)))
            if not rows:
                self.append("No Channels are open. First load the originals using Dragonfly's normal Open/Import command.")
            for row in rows[:20]:
                dims = " x ".join(map(str, row.get("dimensions_xyzt", [])[:3]))
                status = "; ".join(row["reasons"]) or "available for a pixel check when dimensions match"
                self.append("  %s [%s]: %s" % (row["title"], dims, status))
            if len(rows) > 20:
                self.append("Remaining volumes will appear in Save placement report.")
            for _, meta in self.entries:
                self.log_reference_status(meta)
        except Exception as error:
            self.append("Cannot list open volumes: " + str(error))

    def choose_reference(self, meta, parent):
        try:
            return find_reference(meta)
        except ReferenceChoiceRequired as choice:
            labels = ["%d. %s [%d x %d x %d]" % (i+1, c.getTitle(), c.getXSize(), c.getYSize(), c.getZSize())
                      for i, c in enumerate(choice.channels)]
            selected, accepted = QtWidgets.QInputDialog.getItem(
                parent, "Select the original reference volume",
                "Choose the original for %s. Every imported voxel will be verified." % meta.name,
                labels, 0, False)
            if not accepted:
                raise Cancelled()
            return choice.channels[labels.index(selected)]

    def import_files(self):
        stride = int(self.sampling.currentData())
        self.set_busy(True)
        progress = QtWidgets.QProgressDialog("Preparing volume...", "Cancel", 0, 1000, self)
        progress.setWindowTitle("Importing ZEISS TXM")
        progress.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        try:
            for number, (path, meta) in enumerate(self.entries):
                if progress.wasCanceled():
                    break
                def update(done, total):
                    progress.setLabelText("%d/%d: %s\nSlice %d/%d" %
                                          (number+1, len(self.entries), meta.name, done, total))
                    progress.setValue(int(1000*done/max(total, 1)))
                    QtWidgets.QApplication.processEvents()
                    if progress.wasCanceled():
                        raise Cancelled()
                try:
                    reference = self.choose_reference(meta, progress)
                    profile = None if reference is not None else calibration.get_profile(meta)
                    if reference is not None:
                        self.append("Checking against open volume: " + reference.getTitle())
                    _, report = import_txm(path, stride, update, meta.geometry_header_sha256,
                                           reference=reference, profile=profile)
                    self.import_results.append(report)
                    self.append("Imported: " + meta.name + " (" + report["placement_status"] + ")")
                    if report["reference_voxels_verified"]:
                        self.append("Checked every imported voxel: " + format(report["verified_voxel_count"], ","))
                        try:
                            ready = calibration.record(report)
                            if ready:
                                self.append("Calibration saved. Standalone imports are enabled for this supported file family.")
                            elif calibration.load()["profiles"].get(meta.dtype, {}).get("conflict"):
                                self.append("Calibration conflict: standalone imports are disabled. Save the placement report for review.")
                            elif report.get("native_model_matches"):
                                self.append("Reference check passed. One more consistent reference at a different voxel size is needed.")
                            else:
                                self.append("Reference matched, but its transform cannot calibrate the standalone model.")
                        except Exception as error:
                            self.append("Reference check passed; calibration could not be saved: " + str(error))
                except Cancelled:
                    self.append("Cancelled. The unfinished volume was removed; completed imports remain.")
                    break
                except Exception as error:
                    self.append("Failed: " + meta.name + ": " + str(error))
                    traceback.print_exc()
                    failure = {"name": meta.name, "status": "failed", "error": str(error)}
                    try:
                        failure["reference_lookup"] = inspect_references(meta)[1]
                    except Exception as lookup_error:
                        failure["reference_lookup_error"] = str(lookup_error)
                    self.import_results.append(failure)
        finally:
            progress.close()
            progress.deleteLater()
            self.set_busy(False)

    def save_report(self):
        from ORSModel import Channel
        name = "dragonfly_txm_placement_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
        downloads = Path.home() / "Downloads"
        suggested = (downloads if downloads.is_dir() else Path.home()) / name
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save placement report for open volumes", str(suggested), "JSON (*.json)")
        if not path:
            return
        try:
            report = {"plugin_version": VERSION, "time_utc": datetime.now(timezone.utc).isoformat(),
                      "system": platform.system(), "python_version": platform.python_version(),
                      "coordinate_mapping_validated": bool(self.import_results) and all(r.get("coordinate_mapping_validated", False) for r in self.import_results),
                      "selected_files": [meta.report(int(self.sampling.currentData())) for _, meta in self.entries],
                      "import_results": self.import_results, "open_channels": [],
                      "reference_lookup": [{"name": meta.name, "open_volumes": inspect_references(meta)[1]}
                                           for _, meta in self.entries]}
            try:
                report["calibration"] = calibration.load()
            except Exception as error:
                report["calibration"] = {"error": str(error)}
            for channel in Channel.getAllInstances():
                try:
                    report["open_channels"].append(channel_report(channel))
                except Exception as error:
                    report["open_channels"].append({"error": str(error)})
            Path(path).write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
            self.append("Saved report: " + path)
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Could not save report", str(error))

    def install(self):
        from .install import candidate_directory, install_to
        directory = candidate_directory()
        if directory is None:
            chosen = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Dragonfly's pythonUserExtensions/Plugins folder")
            if not chosen:
                return
            directory = Path(chosen)
        try:
            path, backup = install_to(directory)
            self.append("Installed: " + path)
            if backup:
                self.append("Previous version backed up: " + backup)
            QtWidgets.QMessageBox.information(self, "Installed", "Restart Dragonfly, then choose File > Import ZEISS TXM.")
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Could not install", str(error))


class ImportDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__(QtWidgets.QApplication.activeWindow())
        self.setWindowTitle("ZEISS TXM Importer " + VERSION)
        self.resize(1050, 640)
        self.panel = ImportPanel(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.panel)

    def reject(self):
        if not self.panel.busy:
            super().reject()

    def closeEvent(self, event):
        if self.panel.busy:
            event.ignore()
        else:
            super().closeEvent(event)


def launch():
    window = ImportDialog()
    _windows.append(window)
    window.show()
    window.raise_()
    window.activateWindow()
    return window
