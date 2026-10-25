"""Build a clean submission archive from the final working tree."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {'dataset', '.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache'}
EXCLUDE_FILES = {'output.csv', 'sample_output.generated.csv', 'log.txt', 'code.zip', '.DS_Store'}
ARCHIVES = {'.zip', '.tar', '.gz', '.tgz', '.7z', '.rar', '.bz2', '.xz', '.zst'}


def main():
    paths = [ROOT / 'README.md', *sorted((ROOT / 'code').rglob('*'))]
    with ZipFile(ROOT / 'code.zip', 'w', ZIP_DEFLATED) as archive:
        for path in paths:
            relative = path.relative_to(ROOT)
            if not path.is_file() or EXCLUDE_DIRS.intersection(relative.parts):
                continue
            if path.name in EXCLUDE_FILES or path.suffix in ARCHIVES | {'.pyc', '.pyo'}:
                continue
            archive.write(path, relative.as_posix())
        for report in ('evaluation_report.md', 'usage_report.md'):
            archive.write(ROOT / 'code' / 'evaluation' / report, 'evaluation/' + report)
    with ZipFile(ROOT / 'code.zip') as archive:
        required = {'README.md', 'code/main.py', 'code/evaluation/evaluation_report.md',
                    'code/evaluation/usage_report.md', 'evaluation/evaluation_report.md',
                    'evaluation/usage_report.md'}
        assert required <= set(archive.namelist())
        assert archive.testzip() is None
        print(f'Packaged {len(archive.namelist())} files')


if __name__ == '__main__':
    main()
