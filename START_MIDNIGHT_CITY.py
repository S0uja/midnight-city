from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def find_first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def auto_find_model() -> Path | None:
    candidates = [
        Path(r"C:\AI\MidnightBrain_v2_MapAgnostic\models\Qwen3-4B-Nymphaea-RP"),
        Path(r"C:\AI\MidnightBrain_v2_MapAgnostic\models"),
        ROOT / "models" / "Qwen3-4B-Nymphaea-RP",
        ROOT / "models",
    ]
    p = find_first_existing(candidates[:1])
    if p and (p / "config.json").exists():
        return p
    for base in candidates:
        if not base.exists():
            continue
        if (base / "config.json").exists():
            return base
        for child in base.iterdir():
            if child.is_dir() and (child / "config.json").exists():
                return child
    return None


def auto_find_adapter() -> Path | None:
    candidates = [
        Path(r"C:\AI\MidnightBrain_v2_MapAgnostic\output\MidnightBrain-v3\adapter"),
        ROOT / "adapter",
        ROOT / "output" / "MidnightBrain-v3" / "adapter",
    ]
    for p in candidates:
        if (p / "adapter_model.safetensors").exists():
            return p
    return None


def main() -> int:
    model = auto_find_model()
    adapter = auto_find_adapter()

    print("=" * 68)
    print("MIDNIGHT CITY - LOCAL MIDNIGHTBRAIN V25")
    print("=" * 68)
    print("Project:", ROOT)
    print("Model:", model if model else "NOT FOUND")
    print("Adapter:", adapter if adapter else "NOT FOUND")
    print()

    if model is None:
        print("[ERROR] Transformers model not found.")
        print()
        print("Expected default path:")
        print(r"  C:\AI\MidnightBrain_v2_MapAgnostic\models\Qwen3-4B-Nymphaea-RP")
        print()
        print("You can override it with MIDNIGHT_BRAIN_MODEL.")
        input("Press Enter to close...")
        return 1

    if adapter is None:
        print("[ERROR] MidnightBrain adapter not found.")
        print()
        print("Expected default path:")
        print(r"  C:\AI\MidnightBrain_v2_MapAgnostic\output\MidnightBrain-v3\adapter")
        print()
        print("You can override it with MIDNIGHT_BRAIN_ADAPTER.")
        input("Press Enter to close...")
        return 1

    os.environ["MIDNIGHT_BRAIN_MODEL"] = str(model)
    os.environ["MIDNIGHT_BRAIN_ADAPTER"] = str(adapter)

    py = shutil.which("py")
    python = shutil.which("python") or sys.executable
    if py:
        cmd = [py, "-3", str(ROOT / "midnight_city_server_local.py")]
    else:
        cmd = [python, str(ROOT / "midnight_city_server_local.py")]

    print("Starting server...")
    print("Close this window to stop the game.")
    print()
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
