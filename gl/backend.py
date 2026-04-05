"""
OpenGL backend configuration and context initialization.

Applies PyOpenGL performance and correctness flags (ERROR_CHECKING, ERROR_LOGGING,
ERROR_ON_COPY) before any GL import, then exposes a GLConfig singleton that is
populated with runtime-detected capabilities by initialize_context().

Usage
-----
Call initialize_context() exactly once after the OpenGL context and window have
been created. All other modules should then import GL, GLU, and config from here
rather than importing PyOpenGL directly.

    from gl_backend import GL, GLU, config, initialize_context

    initialize_context()  # call once at startup

    if config.USE_IMMUTABLE_STORAGE:
        GL.glTexStorage2D(...)

Environment
-----------
GL_DEBUG_MODE : str, optional
    Set to "1" to enable PyOpenGL error checking, error logging, and the
    KHR_debug callback via enable_gl_debug_output(). Defaults to "0".
    Ignored on macOS, where GL debug callbacks are not supported.

Requires
--------
Python >= 3.x, PyOpenGL, OpenGL >= 4.1
"""

import logging
import os
import platform
import sys
from dataclasses import dataclass

if 'OpenGL.GL' in sys.modules:
    logging.getLogger(__name__).warning(
        "OpenGL.GL was imported before GLConfig could apply optimizations. "
        "PyOpenGL error checking may still be active."
    )

import OpenGL

_DEBUG_ENV = os.environ.get("GL_DEBUG_MODE", "0") == "1"

OpenGL.ERROR_ON_COPY = True

if not _DEBUG_ENV:
    OpenGL.ERROR_CHECKING = False
    OpenGL.ERROR_LOGGING = False
else:
    OpenGL.ERROR_CHECKING = True

try:
    from OpenGL import GL as _GL
    from OpenGL import GLU as _GLU
except ImportError as e:
    raise ImportError(
        "PyOpenGL not found. Install it with: pip install PyOpenGL"
    ) from e


@dataclass
class GLConfig:
    DEBUG_MODE: bool = _DEBUG_ENV and platform.system() != "Darwin"
    USE_IMMUTABLE_STORAGE: bool = False
    FORCE_UNPACK_ALIGNMENT_1: bool = True


config = GLConfig()


def initialize_context():
    """Run this once after window creation."""
    logger = logging.getLogger("GLBackend")

    # Warn explicitly when macOS silently suppresses debug mode so
    # operators are not left wondering why GL_DEBUG_MODE=1 had no effect.
    if _DEBUG_ENV and platform.system() == "Darwin":
        logger.warning(
            "GL debug output is disabled on macOS — Apple's OpenGL "
            "implementation does not support KHR_debug callbacks."
        )

    try:
        version_str = _GL.glGetString(_GL.GL_VERSION)
        if version_str:
            # Version strings can be "4.6.0 <vendor info>"; split on space first,
            # then on '.' to isolate the numeric part reliably.
            numeric_part = version_str.decode().split()[0].split('.')
            major_ver = int(numeric_part[0])
            minor_ver = int(numeric_part[1]) if len(numeric_part) > 1 else 0
        else:
            major_ver, minor_ver = 3, 0  # Assume at least 3.0 if unknown.

        has_immutable = False

        if major_ver >= 4:
            # In Core Profile glGetString(GL_EXTENSIONS) is illegal; enumerate
            # by index instead.
            try:
                num_exts = int(_GL.glGetIntegerv(_GL.GL_NUM_EXTENSIONS))
                extensions = {
                    _GL.glGetStringi(_GL.GL_EXTENSIONS, i).decode()
                    for i in range(num_exts)
                }

                is_42_or_later = (major_ver > 4) or (
                        major_ver == 4 and minor_ver >= 2)
                if "GL_ARB_texture_storage" in extensions or is_42_or_later:
                    has_immutable = True

            except Exception as e:
                logger.warning(f"Could not enumerate extensions: {e}")
        else:
            # Fallback for legacy/compatibility profiles below 4.0.
            try:
                ext_str = _GL.glGetString(_GL.GL_EXTENSIONS)
                if ext_str and b"GL_ARB_texture_storage" in ext_str:
                    has_immutable = True
            except Exception as e:
                logger.debug(f"Legacy extension string unavailable: {e}")

        config.USE_IMMUTABLE_STORAGE = has_immutable

        if has_immutable:
            logger.info("GL Strategy: Immutable Storage (Optimized)")
        else:
            logger.info("GL Strategy: Mutable Storage (Legacy)")

    except Exception as e:
        logger.error(f"Context capability check failed: {e}")
        config.USE_IMMUTABLE_STORAGE = False

    if config.DEBUG_MODE:
        logger.info(
            f"GL Debug Mode: ENABLED (PyOpenGL checking: {OpenGL.ERROR_CHECKING})"
        )
        from cross_platform.qt6_utils.image.gl.debug import (
            enable_gl_debug_output
        )
        enable_gl_debug_output()
    else:
        logger.info("GL Debug Mode: DISABLED (High Performance)")


GL = _GL
GLU = _GLU
