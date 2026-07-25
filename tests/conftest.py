"""Test configuration for the Rehau gateway."""

from pathlib import Path
import sys


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "rehau_neasmart2.0_gateway"
    / "rootfs"
    / "src"
)
sys.path.insert(0, str(SOURCE))
