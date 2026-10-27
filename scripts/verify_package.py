"""Exercise the built portable artifact in a fresh directory, including diagnostics."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcforge import __version__


def main():
    package = ROOT / 'dist' / f'Minecraft-Forge-{__version__}.zip'
    scratch = ROOT / 'local'
    scratch.mkdir(exist_ok=True)
    with zipfile.ZipFile(package) as archive, tempfile.TemporaryDirectory(dir=scratch) as directory:
        assert archive.testzip() is None, 'ZIP CRC failure'
        manifest = json.loads(archive.read('PACKAGE-MANIFEST.json'))
        assert set(manifest['files']) == set(archive.namelist()) - {'PACKAGE-MANIFEST.json'}
        for name, checksum in manifest['files'].items():
            assert not name.startswith(('/', '../', 'local/', 'dist/')) and '..' not in Path(name).parts
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum, name
        archive.extractall(directory)
        for command in (['--version'], ['doctor'], ['self-test'], ['init', 'probe', '--mod-id', 'zipprobe', '--package', 'dev.mcforge.zipprobe', '--name', 'ZIP Probe']):
            subprocess.run([sys.executable, '-m', 'mcforge', *command], cwd=directory, check=True)
    print('Portable artifact checks passed')


if __name__ == '__main__':
    main()
