"""Shader management module for loading and validating shader files."""

from pathlib import Path

SHADER_DIR = Path(__file__).parent

SHADERS = {
    "image_vertex": SHADER_DIR / "image.vert",
    "image_fragment": SHADER_DIR / "image.frag",
    "colorbar_vertex": SHADER_DIR / "colorbar.vert",
    "colorbar_fragment": SHADER_DIR / "colorbar.frag",
}


def _validate_shader_paths(shaders: dict[str, Path]) -> None:
    """
    Validate that all shader files exist.

    Args:
        shaders: Dictionary mapping shader names to file paths.

    Raises:
        FileNotFoundError: If any shader file is missing, with details on all missing files.
    """
    missing = [name for name, path in shaders.items() if not path.exists()]

    if missing:
        raise FileNotFoundError(
            f"Shader files not found: {', '.join(missing)}\n"
            f"Expected location: {SHADER_DIR}"
        )


# Validate shaders on module import
_validate_shader_paths(SHADERS)