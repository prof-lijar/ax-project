# Build on Windows with: python -m PyInstaller --noconfirm KakaoCaptureAgent.spec
from pathlib import Path

root = Path(SPECPATH)
a = Analysis([str(root / 'app' / 'main.py')], pathex=[str(root)],
             datas=[(str(root / 'app' / 'storage' / 'schema.sql'), 'app/storage')],
             hiddenimports=['win32timezone'],
             excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='KakaoCaptureAgent',
          console=False, manifest=str(root / 'app.manifest'))
coll = COLLECT(exe, a.binaries, a.datas, name='KakaoCaptureAgent')
