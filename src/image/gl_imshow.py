import logging
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout

from image.gl.backend import GL
from image.gl.utils import get_surface_format
from image.gl.view import GLFrameViewer
from image.gui.overlay.toolbar import GLToolbar
from image.pipeline.stats import (
    get_frame_stats, FrameStats)
from image.settings.base import ImageSettings
from image.settings.pixels import PixelFormat
from pycore.log.ctx import ContextAdapter
from qtcore.app import Application

logger = ContextAdapter(logging.getLogger(__name__), {})

_APP_INSTANCE = None
_ACTIVE_WINDOWS = []
_SURFACE_FORMAT_SET = False
_ZOOM_STEP = 1.25  # multiply / divide per click


# noinspection PyPep8Naming
class GLImageShow(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent=parent)
        self.settings = ImageSettings()
        self.metadata: FrameStats | None = None
        self._deffered_frame: np.ndarray | None = None

        self.viewer = GLFrameViewer(settings=self.settings,
                                    monitor_performance=False,
                                    parent=self)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        self.layout().addWidget(self.viewer)
        self._setup_toolbar()
        self.setWindowTitle("GL imshow")

    def _setup_toolbar(self):
        # Toolbar — created after viewer so it paints on top
        self._toolbar = GLToolbar(parent=self)

        self.settings.update_setting('zoom_enabled', True)
        self._toolbar.zoom_in_requested.connect(self._zoom_in)
        self._toolbar.zoom_out_requested.connect(self._zoom_out)
        self._toolbar.zoom_reset_requested.connect(self._zoom_reset)
        self._toolbar.raise_()

    # ------------------------------------------------------------------
    # Zoom helpers
    # ------------------------------------------------------------------

    def _zoom_in(self) -> None:
        self._apply_zoom(_ZOOM_STEP)

    def _zoom_out(self) -> None:
        self._apply_zoom(1.0 / _ZOOM_STEP)

    def _zoom_reset(self) -> None:
        """Restore 1:1 pixel mapping."""
        if self.settings.zoom_enabled:
            self.settings.update_setting('zoom', 1)

    def _apply_zoom(self, factor: float) -> None:
        if self.settings.zoom_enabled:
            self.settings.update_setting('zoom',
                                         max(0.05, self.settings.zoom * factor))

    def set_data(self,
                 X: np.ndarray,
                 fmt: Optional["PixelFormat"] = None,
                 vmin: float | None = None,
                 vmax: float | None = None,
                 cmap: str = "viridis",
                 title: str = "GL imshow"):

        if fmt is None:
            fmt = PixelFormat.infer_from_shape(X.shape) or PixelFormat.RGB

        is_scalar_input = (X.ndim == 2) or (X.ndim == 3 and X.shape[2] == 1)
        use_colormap = False
        norm_vmin = vmin
        norm_vmax = vmax

        if is_scalar_input:
            fmt = PixelFormat.MONOCHROME
            use_colormap = True
            if norm_vmin is None:
                norm_vmin = self.metadata.dmin if self.metadata else float(
                    X.min())
            if norm_vmax is None:
                norm_vmax = self.metadata.dmax if self.metadata else float(
                    X.max())
        else:
            if norm_vmin is None: norm_vmin = 0.0
            if norm_vmax is None: norm_vmax = 1.0

        self.settings.format = fmt
        self.settings.norm_vmin = norm_vmin
        self.settings.norm_vmax = norm_vmax
        self.settings.colormap_enabled = use_colormap
        self.settings.colormap_name = cmap
        self.settings.colormap_reverse = cmap.endswith("_r")

        self.setWindowTitle(title)
        self.metadata = get_frame_stats(image=X)

        if self.viewer.is_initialized:
            logger.debug("Uploading image to pinned buffer")
            h, w = X.shape[:2]
            dtype = X.dtype
            pbo, pbo_buf = self.viewer.request_pinned_buffer(width=w, height=h,
                                                             pixel_fmt=fmt,
                                                             dtype=dtype)
            self.viewer.write_to_pinned_buffer(pbo_array=pbo_buf, image=X,
                                               pixel_fmt=fmt)
            self.viewer.present_pinned(pbo_object=pbo, metadata=self.metadata,
                                       width=w, height=h, img_fmt=fmt,
                                       dtype=dtype)
            self.viewer.repaint()
            if GL and hasattr(GL, "glFinish"):
                logger.debug("Syncing GPU")
                GL.glFinish()
            return

        self._deffered_frame = X
        self.update()

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # Keep toolbar pinned to top-right after every resize
        self._toolbar._reposition()

    def keyPressEvent(self, event):  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
            event.accept()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_in()
        elif key == Qt.Key.Key_Minus:
            self._zoom_out()
        elif key == Qt.Key.Key_1:
            self._zoom_reset()
        else:
            super().keyPressEvent(event)

    def showEvent(self, event):  # noqa: N802
        if self._deffered_frame is not None:
            self.viewer.present(self._deffered_frame, self.metadata,
                                self.settings.format)
            GL.glFinish()
            self._deffered_frame = None
        super().showEvent(event)
        self._toolbar.raise_()
        self._toolbar._reposition()

    def closeEvent(self, event):  # noqa: N802
        self.viewer.cleanup()
        return super().closeEvent(event)


def _ensure_app() -> QApplication:
    """
    Return the module-level QApplication, creating it if necessary.
    Respects any QApplication that already exists (e.g. caller-owned).
    Surface format is set exactly once here.
    """
    global _APP_INSTANCE, _SURFACE_FORMAT_SET

    if _APP_INSTANCE is not None:
        return _APP_INSTANCE

    # Respect a pre-existing application instance (e.g. when imshow is used
    # inside a larger app that owns its own QApplication).
    existing = QApplication.instance()
    if existing is not None:
        _APP_INSTANCE = existing
    else:
        _APP_INSTANCE = Application(
            app_name="GL Image Show",
            org_name="pkkenne.dev",
            app_version="0.1.0",
        )
        _APP_INSTANCE.show_splash(min_display_ms=2_000)

    # Global mutation — must happen once, before any GL surface is created.
    if not _SURFACE_FORMAT_SET:
        QSurfaceFormat.setDefaultFormat(get_surface_format())
        _SURFACE_FORMAT_SET = True

    return _APP_INSTANCE


def _window_size(
        app: QApplication, img_w: int, img_h: int
) -> tuple[int, int]:
    """
    Clamp image dimensions to the available screen area.
    Uses logical pixels so HiDPI scaling is handled correctly.
    """
    screen = app.primaryScreen()
    available = screen.availableSize()
    scale = screen.devicePixelRatio()

    max_w = int(available.width() / scale)
    max_h = int(available.height() / scale)

    w = min(img_w, max_w) if img_w > 0 else 800
    h = min(img_h, max_h) if img_h > 0 else 600
    return w, h


def _cleanup(window: GLImageShow) -> None:
    if window in _ACTIVE_WINDOWS:
        _ACTIVE_WINDOWS.remove(window)


# noinspection PyPep8Naming
def imshow(
        X: np.ndarray,
        title: str = "Image",
        cmap: str = "gray",
        fmt: Optional['PixelFormat'] = None,
        vmin: float | None = None,
        vmax: float | None = None,
        block: bool = True,
) -> GLImageShow:
    """
    Drop-in replacement for plt.imshow / cv2.imshow using custom OpenGL.

    Args:
        X:      The numpy array (2D or 3D).
        title:  Window title.
        cmap:   Colormap ('viridis', 'gray', 'magma', 'plasma').
                Ignored if X is RGB/BGR.
        fmt:    Explicit PixelFormat (optional).
        vmin:   Minimum value for normalisation.
        vmax:   Maximum value for normalisation.
        block:  If True, enters the Qt event loop (blocks until all windows
                are closed). If False, shows the window and returns immediately.

    Returns:
        The GLImageShow window instance.
    """
    if X is None:
        raise ValueError("Input array X cannot be None")

    app = _ensure_app()

    window = GLImageShow()

    # WA_DeleteOnClose:      Qt frees the C++ object when the window closes.
    # WA_OpaquePaintEvent:   Skips background clearing — GL fills every pixel.
    # WA_NoSystemBackground: Suppresses the flicker from the default OS fill.
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    window.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
    window.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    img_h, img_w = X.shape[:2]
    window.resize(*_window_size(app, img_w, img_h))

    # Load data before show() so the first paint is never blank.
    window.set_data(X=X, fmt=fmt, vmin=vmin, vmax=vmax, cmap=cmap, title=title)
    window.show()

    # finish_splash delegates to QSplashScreen.finish(window), which waits
    # for the window's first exposed event before hiding the splash.
    app.finish_splash(window)

    # Keep the window alive against the GC for the lifetime of the session.
    _ACTIVE_WINDOWS.append(window)

    # Default-argument capture avoids the late-binding closure problem.
    # destroyed emits a QObject* argument, so the lambda accepts and ignores it.
    window.destroyed.connect(lambda _, w=window: _cleanup(w))

    if block:
        app.exec()

    return window
