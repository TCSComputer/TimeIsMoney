# build.py — robust builder (auto-detects Tcl/Tk paths via tkinter)
import os, sys, shutil
from pathlib import Path

def main():
    try:
        import PyInstaller.__main__ as pim
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])
        import PyInstaller.__main__ as pim

    # Ask Tk where its libraries live (works from any venv)
    import tkinter as tk
    _r = tk.Tk(); _r.withdraw()
    tcl_lib = Path(_r.tk.call("info", "library"))          # ...\tcl8.6  or ...\tcl8.7
    tk_lib  = Path(_r.tk.globalgetvar("tk_library"))        # ...\tk8.6   or ...\tk8.7
    _r.destroy()

    tcl_ver = tcl_lib.name
    tk_ver  = tk_lib.name

    proj = Path(__file__).parent.resolve()
    exe_name = "Phone Support Timer"

    # Clean old artifacts
    for d in ("build", "dist", "__pycache__"):
        shutil.rmtree(proj / d, ignore_errors=True)

    # Windows uses ';' between src and dest in --add-data
    add_data = [
        f"{tcl_lib}{os.pathsep}tcl/{tcl_ver}",
        f"{tk_lib}{os.pathsep}tcl/{tk_ver}",
    ]

    args = [
        "--clean", "--noconfirm", "--onefile", "--windowed",
        f"--name={exe_name}",
        f"--icon={proj / 'support.ico'}",
        "--hidden-import=tkinter", "--hidden-import=_tkinter",
        *(f"--add-data={x}" for x in add_data),
        str(proj / "call_timer.py"),
    ]

    print("Using:", tcl_lib, tk_lib)
    print("PyInstaller args:\n  " + "\n  ".join(args))
    pim.run(args)
    print("\nBuilt:", proj / "dist" / f"{exe_name}.exe")

if __name__ == "__main__":
    main()
