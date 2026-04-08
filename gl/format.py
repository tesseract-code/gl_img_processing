import logging
from functools import lru_cache
from typing import Tuple, Union, Any

from cross_platform.qt6_utils.image.gl.backend import GL
import numpy as np

from cross_platform.qt6_utils.image.settings.pixels import PixelFormat

logger = logging.getLogger(__name__)

# Format: (gl_format, gl_internal_format, gl_type)
type GLTextureSpec = tuple[int, int, int]


@lru_cache(maxsize=32)
def _resolve_gl_dtype_params(dtype_name: str) -> Tuple[int, str]:
    """
    Resolves canonical numpy dtype name to (GL_TYPE, Internal Suffix).
    Args:
        dtype_name: Canonical string from np.dtype.name (e.g. 'float32', 'uint8')
    """
    match dtype_name:
        case 'uint8':
            return GL.GL_UNSIGNED_BYTE, '8'
        case 'int8':
            return GL.GL_BYTE, '8_SNORM'
        case 'uint16':
            return GL.GL_UNSIGNED_SHORT, '16'
        case 'int16':
            return GL.GL_SHORT, '16_SNORM'
        case 'float16':
            return GL.GL_HALF_FLOAT, '16F'
        case 'float32':
            return GL.GL_FLOAT, '32F'
        case 'float64':
            # Map float64 to float32 storage for compatibility
            return GL.GL_DOUBLE, '32F'
        case _:
            raise ValueError(f"Unsupported numpy dtype for GL Texture: {dtype_name}")


@lru_cache(maxsize=64)
def _resolve_gl_format_base(fmt_name: str) -> Tuple[int, str]:
    """
    Resolves PixelFormat name to (GL_FORMAT, Base Internal String).
    Args:
        fmt_name: String name of the PixelFormat enum (e.g. 'RGB', 'BGRA')
    """
    match fmt_name:
        # --- 3 Channel ---
        case 'RGB' | 'YUV444':
            return GL.GL_RGB, "GL_RGB"
        case 'BGR':
            return GL.GL_BGR, "GL_RGB"

        # --- 4 Channel ---
        case 'RGBA':
            return GL.GL_RGBA, "GL_RGBA"
        case 'BGRA':
            return GL.GL_BGRA, "GL_RGBA"

        # --- 1 Channel / Grayscale / Planar ---
        case 'MONOCHROME' | 'GRAY' | 'YUV420' | 'YUV422' | 'NV12' | 'NV21':
            return GL.GL_RED, "GL_R"

        # --- 2 Channel ---
        case 'RG':
            return GL.GL_RG, "GL_RG"

        case _:
            raise ValueError(f"Unsupported PixelFormat: {fmt_name}")


@lru_cache(maxsize=128)
def get_gl_texture_spec(fmt: Any, dtype: Union[str, np.dtype, type]) -> GLTextureSpec:
    """
    Determines the correct OpenGL texture parameters.

    Args:
        fmt: PixelFormat enum member or string name.
        dtype: Numpy dtype (e.g., np.float32), string ('float32'), or type.

    Returns:
        (gl_format, gl_internal_format, gl_type)
    """
    # 1. Normalize Dtype (Robustly)
    # This handles: 'float32', np.float32, np.dtype('float32'), float
    try:
        dtype_str = np.dtype(dtype).name
    except TypeError:
        # Fallback if weird object passed
        dtype_str = str(dtype)

    # 2. Normalize Format
    fmt_name = fmt.name if hasattr(fmt, 'name') else str(fmt)

    # 3. Resolve Parameters (Cached)
    gl_type, type_suffix = _resolve_gl_dtype_params(dtype_str)
    gl_format, base_internal = _resolve_gl_format_base(fmt_name)

    # 4. Construct Internal Format Constant
    internal_attr = f"{base_internal}{type_suffix}"

    try:
        gl_internal = getattr(GL, internal_attr)
    except AttributeError:
        # Fallback to base format (e.g. if SNORM specific missing)
        logger.debug(f"GL Internal format {internal_attr} missing. Using {base_internal}.")
        try:
            gl_internal = getattr(GL, base_internal)
        except AttributeError:
            raise ValueError(f"Critical: Base GL format {base_internal} not found.")

    return gl_format, gl_internal, gl_type
