from pathlib import Path
import sys

from PyInstaller.utils.hooks import copy_metadata, get_package_paths


project = Path(SPEC).resolve().parent
python_root = Path(sys.base_prefix)
debug_console = "--debug-console" in sys.argv
bundle_name = "PostureCompanionDebug" if debug_console else "PostureCompanion"
_, mediapipe_root = get_package_paths("mediapipe")
hidden = [
    "cv2",
    "pystray._win32",
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
]
datas = copy_metadata("mediapipe") + [
    (str(project / "models" / "pose_landmarker_lite.task"), "models"),
    (str(python_root / "tcl" / "tcl8.6"), "_tcl_data"),
    (str(python_root / "tcl" / "tk8.6"), "_tk_data"),
]
tk_binaries = [
    (str(python_root / "DLLs" / "_tkinter.pyd"), "."),
    (str(python_root / "DLLs" / "tcl86t.dll"), "."),
    (str(python_root / "DLLs" / "tk86t.dll"), "."),
]

a = Analysis(
    [str(project / "run_app.py")],
    pathex=[str(project / "src")],
    binaries=[
        (str(Path(mediapipe_root) / "tasks" / "c" / "libmediapipe.dll"), "mediapipe/tasks/c"),
        *tk_binaries,
    ],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[str(project / "hooks")],
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
    runtime_hooks=[],
    excludes=["pytest", "IPython", "jupyter", "notebook"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=bundle_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=debug_console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project / "assets" / "posture_companion.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=bundle_name,
)
