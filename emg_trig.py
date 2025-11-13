@QtCore.pyqtSlot()
def handle_emergency_trigger(self):
    logger.warning("EMERGENCY triggered — performing full reset")
    self.emergency_active = True

    try:
        if hasattr(self.ui, "menu_window") and self.ui.menu_window.isVisible():
            self.ui.menu_window.close()
            logger.info("Task select window closed due to emergency.")
    except Exception as e:
        logger.error(f"Failed to close menu window: {e}")

    try:
        self._stop_timer()
    except Exception:
        pass
    try:
        self.model_handler.stop_validation("EMERGENCY")
        self.model_handler.reset()
    except Exception:
        pass

    if self.io_handler:
        try:
            self.io_handler._emergency_mode = True
            self.io_handler.stop_rfid()
            self.io_handler.release_camera()
            self.io_handler._emg_open()
        except Exception:
            pass

    if hasattr(self.ui, "show_emergency"):
        self.ui.show_emergency()
    if hasattr(self.ui, "blink_emergency"):
        self.ui.blink_emergency()

@QtCore.pyqtSlot()
def handle_emergency_clear(self):
    if not self.emergency_active:
        logger.debug("Ignore redundant emergency_clear signal.")
        return
    logger.info("Emergency cleared — restarting system")
    self.emergency_active = False

    if self.io_handler:
        try:
            self.io_handler._emergency_mode = False
            self.io_handler.start_rfid_thread()
        except Exception:
            pass

    if hasattr(self.ui, "emergency_timer"):
        self.ui.emergency_timer.stop()
    if hasattr(self.ui, "hide_emergency"):
        self.ui.hide_emergency()
    QtCore.QTimer.singleShot(200, self.ui.show_scan_overlay)