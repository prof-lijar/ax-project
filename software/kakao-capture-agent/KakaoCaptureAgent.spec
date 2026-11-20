# Single-file Windows executable, including Python and native dependencies.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis([str(root / 'app' / 'main.py')], pathex=[str(root)],
             datas=[(str(root / 'app' / 'storage' / 'schema.sql'), 'app/storage'),
                    (str(root / 'app' / 'automation' / 'read_chat_text.ps1'), 'app/automation'),
                    (str(root / 'app' / 'assets' / 'voyageri.png'), 'app/assets'),
                    (str(root / 'app' / 'assets' / 'voyageri.ico'), 'app/assets')],
             hiddenimports=['win32timezone'],
             excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='VoyagerI',
          console=False, upx=False, manifest=str(root / 'app.manifest'),
          icon=str(root / 'app' / 'assets' / 'voyageri.ico'),
          version=str(root / 'windows-version-info.txt'))
