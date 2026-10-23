#!/usr/bin/env python3
"""Vypise, co sa da zistit o motorovej kniznici AMD bez cítania zdrojov na GitHube.

Spusti s root pravami a cestami ako dashboard:
  sudo env PYTHONPATH=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib \
           LD_LIBRARY_PATH=/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib \
           python3 tools/inspect_motor_lib.py

Vypisy posli (alebo si ich precitaj): z nich sa doplni kd240sync/motor/foc_lib.py.
"""
import glob
import importlib
import inspect
import os
import sys

PREFIX = "/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl"
LIB = PREFIX + "/lib"
DASH = PREFIX + "/share/foc-motor-ctrl/dashboard"


def show_module(name):
    try:
        mod = importlib.import_module(name)
    except Exception as e:                     # noqa: BLE001
        print(f"  import {name} zlyhal: {e!r}")
        return
    print(f"  modul {name}: {getattr(mod, '__file__', '?')}")
    for n in sorted(dir(mod)):
        if n.startswith("_"):
            continue
        obj = getattr(mod, n)
        print(f"    {n}  [{type(obj).__name__}]")
        if inspect.isclass(obj):
            for m in sorted(dir(obj)):
                if not m.startswith("_"):
                    doc = (getattr(obj, m).__doc__ or "").strip().splitlines()
                    print(f"        .{m}  {doc[0] if doc else ''}")


def main():
    print("== subory v", LIB)
    for f in sorted(glob.glob(LIB + "/*")):
        print("  ", os.path.basename(f))
    print("\n== python moduly (pybind11 .so)")
    for f in sorted(glob.glob(LIB + "/*.so")):
        base = os.path.basename(f).split(".")[0]
        if base.startswith("lib"):
            continue        # bezne zdielane kniznice, nie python moduly
        show_module(base)
    print("\n== zdroj dashboardu:", DASH)
    for f in sorted(glob.glob(DASH + "/**/*.py", recursive=True)):
        print("  ", f)
        with open(f, errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                if line.lstrip().startswith(("import ", "from ")):
                    print(f"      {i}: {line.rstrip()}")
    print("\nPrecitaj dashboard (cat subor) - ukazuje, ako sa kniznica vola.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, LIB)
    raise SystemExit(main())
