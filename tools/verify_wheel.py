#!/usr/bin/env python3
"""Install the built wheel in isolation and verify its packaged schemas."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    wheels = tuple((root / "dist").glob("asterix_codec-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one wheel in dist, found {len(wheels)}")
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required to verify the wheel")
    script = (
        "from asterix import SchemaRegistry; "
        "r=SchemaRegistry.builtin(); "
        "assert len(r.keys()) == 75; "
        "assert all(r.get(k.category, k.edition, k.kind) for k in r.keys())"
    )
    subprocess.run(
        [uv, "run", "--isolated", "--with", str(wheels[0]), "python", "-c", script],
        check=True,
        cwd=root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
