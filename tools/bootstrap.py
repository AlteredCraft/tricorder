"""Install the pinned factory sources and project-local ESP32-P4 toolchain."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    pins = json.loads((ROOT/'tools/factory-sources.lock.json').read_text())
    for relative, source in pins['repositories'].items():
        path = ROOT/relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            run(['git', 'clone', '--no-checkout', source['url'], path])
            run(['git', '-C', path, 'checkout', '--detach', source['commit']])
        actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != source['commit']:
            raise SystemExit(f'{path}: expected {source["commit"]}, got {actual}; preserve and inspect local work')
        dirty = subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no'], text=True)
        if dirty:
            raise SystemExit(f'{path}: tracked source changes; preserve and inspect local work')
        if (path/'.gitmodules').exists():
            run(['git', '-C', path, 'submodule', 'update', '--init', '--recursive', '--depth', '1'])
    env = os.environ.copy()
    env.update(UV_CACHE_DIR=str(ROOT/'.tools/uv-cache'),
               UV_PYTHON_INSTALL_DIR=str(ROOT/'.tools/python'),
               IDF_TOOLS_PATH=str(ROOT/'.tools/espressif'))
    python = ROOT/'.tools/python-env/bin/python'
    if not python.exists():
        run(['uv', 'venv', ROOT/'.tools/python-env', '--python', pins['host_python']], env=env)
    run(['uv', 'pip', 'install', '--python', python,
         f'esptool=={pins["inspection_esptool"]}', f'cmake=={pins["cmake"]}', f'ninja=={pins["ninja"]}'], env=env)
    base_python = subprocess.check_output([str(python), '-c', 'import sys; print(sys._base_executable)'], text=True).strip()
    idf_tools = ROOT/'.tools/esp-idf/tools/idf_tools.py'
    run([base_python, idf_tools, 'install', '--targets=esp32p4'], env=env)
    run([base_python, idf_tools, 'install-python-env'], env=env)
    print('Ready: tools/idf.sh -C firmware build')


if __name__ == '__main__':
    main()
