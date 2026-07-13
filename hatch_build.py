"""Hatch build hook that embeds the compiled browser app in wheels."""

from __future__ import annotations

import shutil
import subprocess
from importlib import import_module
from pathlib import Path
from typing import Any

# Hatchling is provided by the PEP 517 build environment, not by the project
# runtime. Loading its hook interface here keeps that boundary explicit.
BuildHookInterface = import_module("hatchling.builders.hooks.plugin.interface").BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Build and force-include the SPA for standard wheel distributions."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "wheel" or version != "standard":
            return

        npm = shutil.which("npm")
        if npm is None:
            msg = "Building the meeple wheel requires npm (Node.js 24 or newer)."
            raise RuntimeError(msg)

        frontend = Path(self.root) / "frontend"
        subprocess.run([npm, "ci"], cwd=frontend, check=True)
        subprocess.run([npm, "run", "build"], cwd=frontend, check=True)

        dist = frontend / "dist"
        if not (dist / "index.html").is_file():
            msg = f"Frontend build did not produce {dist / 'index.html'}"
            raise RuntimeError(msg)
        build_data["force_include"][str(dist)] = "meeple/web/static"
