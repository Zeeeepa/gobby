"""
Core path utilities for Gobby package.

This module provides stable path resolution utilities that work in both
development (source) and installed (package) modes without CLI dependencies.
"""

from pathlib import Path

__all__ = ["get_package_root", "get_install_dir"]


def get_package_root() -> Path:
    """Get the root directory of the gobby package.

    Returns:
        Path to src/gobby/ (the package root directory)
    """
    import gobby

    return Path(gobby.__file__).parent


def get_install_dir() -> Path:
    """Get the gobby install directory.

    Checks for source directory (development mode) first,
    falls back to package directory. This handles both:
    - Development: src/gobby/install/
    - Installed package: <site-packages>/gobby/install/

    Returns:
        Path to the install directory
    """
    import gobby

    package_install_dir = Path(gobby.__file__).parent / "install"

    # Try to find source directory (project root) for development mode
    current = Path(gobby.__file__).resolve()
    source_install_dir = None

    for parent in current.parents:
        potential_source = parent / "src" / "gobby" / "install"
        if potential_source.exists():
            source_install_dir = potential_source
            break

    if source_install_dir and source_install_dir.exists():
        return source_install_dir
    return package_install_dir
