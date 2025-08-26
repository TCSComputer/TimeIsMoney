# build.py — robust PyInstaller build without creating a Tk root
import os, sys, shutil
from pathlib import Path

def main():
    try:
        import PyInstaller.__main__ as pim
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])
        import PyInstaller.__main__ as pim

    proj = Path(__file__).parent.resolve()
    exe_name = "Phone Support Timer"

    # Locate Tcl/Tk under the *base* interpreter (not the venv)
    base = Path(sys.base_prefix)  # e.g. C:\Users\...\Python313
    tcl_root = base / "tcl"
    if not tcl_root.exists():
        raise SystemExit(f"Couldn't find Tcl root: {tcl_root}")

    def pick(globpat):
        cands = sorted(tcl_root.glob(globpat), key=lambda p: p.name)
        if not cands:
            raise SystemExit(f"No matches for {globpat} under {tcl_root}")
        return cands[-1].name  # highest (e.g., tcl8.6 or tcl8.7)

    tcl_ver = pick("tcl8.*")
    tk_ver  = pick("tk8.*")

    # Windows: use os.pathsep (';') between src and dest in --add-data
    add_data = [
        f"{(tcl_root / tcl_ver)}{os.pathsep}tcl/{tcl_ver}",
        f"{(tcl_root / tk_ver)}{os.pathsep}tcl/{tk_ver}",
    ]

    # Clean old artifacts
    for d in ("build", "dist", "__pycache__"):
        shutil.rmtree(proj / d, ignore_errors=True)

    args = [
        "--clean", "--noconfirm", "--onefile", "--windowed",
        f"--name={exe_name}",
        f"--icon={proj / 'support.ico'}",
        "--hidden-import=tkinter", "--hidden-import=_tkinter",
        *(f"--add-data={x}" for x in add_data),
        str(proj / "call_timer.py"),
    ]

    print("Base Python:", base)
    print("Using Tcl dirs:", tcl_root / tcl_ver, "and", tcl_root / tk_ver)
    print("PyInstaller args:\n  " + "\n  ".join(args))

    pim.run(args)
    print("\nBuilt:", proj / "dist" / f"{exe_name}.exe")

if __name__ == "__main__":
    main()