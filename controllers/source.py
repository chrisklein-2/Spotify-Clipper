from audio_backends import default_device_index, list_capture_devices, loopback_help, native_samplerate
from ui.dialogs import SourceDialog 
from PySide6.QtWidgets import QDialog, QMessageBox

class SourceMixin:
     # ---- source management-----------------------------------
    
        def resolve_source(self):
            devices = list_capture_devices()
            chosen = None
            for device in devices:
                if device.label == self.source_label:
                    chosen = device
                    break
            if chosen is None:
                index = default_device_index(devices)
                chosen = devices[index] if 0 <= index < len(devices) else None
            self.apply_source(chosen, remember=False)
    
        def apply_source(self, device, remember=True):
            self.device = device
            if device is None:
                self.source_btn.setText("Source: none \u2014 click to choose")
                self.source_btn.setToolTip(loopback_help())
                self.statusBar().showMessage("No capture source.  " + loopback_help())
                return
            label = device.label
            self.source_btn.setText(label if len(label) <= 32 else label[:31] + "\u2026")
            self.source_btn.setToolTip(f"{label}\n\nClick to change.   [Ctrl+I]")
            if remember:
                self.source_label = label
                self.settings.setValue("source_label", label)
            rate = native_samplerate(device)
            if rate is not None:
                for i in range(self.sr_box.count()):
                    if self.sr_box.itemData(i) == rate:
                        self.sr_box.setCurrentIndex(i)
                        break
            self.check_rate_match()
    
        def choose_source(self):
            if self.recorder is not None:
                QMessageBox.information(self, "Recording", "Stop recording first.")
                return
            dialog = SourceDialog(self.source_label, self)
            if dialog.exec() == QDialog.Accepted and dialog.chosen():
                self.apply_source(dialog.chosen())
    
        def check_rate_match(self, *_):
            rate = native_samplerate(self.device)
            want = self.sr_box.currentData()
            if rate and want and rate != want:
                self.statusBar().showMessage(
                    f"Note: the device runs at {rate} Hz but you chose {want} Hz. "
                    f"Windows will resample, which can add grit.",
                    12000,
                )
    