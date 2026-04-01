from pathlib import Path

SHADER_DIR = Path(__file__).parent

SHADERS = {
    "image_vertex": SHADER_DIR / "image.vert",
    "image_fragment": SHADER_DIR / "image.frag",
    "colorbar_vertex": SHADER_DIR / "colorbar.vert",
    "colorbar_fragment": SHADER_DIR / "colorbar.frag",
}

# Validate shader files exist
def _validate_shader_path(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Shader file not found: {path}")
    return path