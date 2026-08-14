# PyInstaller spec — onedir build with two exes sharing one bundle:
#   AfterScope.exe     windowed (watchdog, wizard) — no console flash
#   AfterScopeCli.exe  console  (doctor, export, backup, migrate --ingest)
# Build on Windows:  pyinstaller deploy/after_scope.spec
# onedir (not onefile) deliberately: far fewer antivirus false positives.

from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("../src/after_scope/db/schema", "after_scope/db/schema"),
    ("../src/after_scope/wizard/style.qss", "after_scope/wizard"),
    ("../src/after_scope/report/templates", "after_scope/report/templates"),
]
datas += collect_data_files("pylibCZIrw")

hidden = ["pylibCZIrw", "czifile", "pystray", "PIL", "win32api"]

a = Analysis(
    ["../src/after_scope/__main__.py"],
    pathex=["../src"],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "IPython", "jupyter"],
)
pyz = PYZ(a.pure)

exe_gui = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="AfterScope",
    console=False,
    icon=None,
)
exe_cli = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="AfterScopeCli",
    console=True,
    icon=None,
)

coll = COLLECT(
    exe_gui,
    exe_cli,
    a.binaries,
    a.datas,
    name="AfterScope",
)
