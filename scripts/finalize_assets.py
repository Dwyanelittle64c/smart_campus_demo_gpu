"""记录固定源码/实际锁文件/第三方许可；不修改旧项目或下载运行数据。"""
import hashlib
import importlib.metadata as metadata
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest_path = ROOT/'assets-manifest.json'
    records = json.loads(manifest_path.read_text('utf-8'))
    license_source = ROOT/'third_party/licenses/Houseplant-CC-BY-4.0.txt'
    license_target = ROOT/'data/scenes/plant/LICENSE.txt'
    if not license_target.exists():
        shutil.copy2(license_source,license_target)
    relative = license_target.relative_to(ROOT).as_posix()
    if not any(row['path']==relative for row in records):
        records.append({'path':relative,'bytes':license_target.stat().st_size,'sha256':hashlib.sha256(license_target.read_bytes()).hexdigest(),
                        'origin':'CC BY4.0完整许可；官方来源见third_party/licenses/sources.json'})
    manifest_path.write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf-8')
    source = ROOT/'third_party/gsplat'
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    assert commit == '937e29912570c372bed6747a5c9bf85fed877bae', 'gsplat版本与验收版本不符'
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', '--quiet'], check=True)
    pin = {'repository':'https://github.com/nerfstudio-project/gsplat','version':'1.5.3',
           'commit':commit,'glm_commit':'33b4a621a697a305bc3a7610d290677b96beb181',
           'algorithm_patches':[], 'license':'Apache-2.0',
           'source_hashes':{name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in ('setup.py','gsplat/rendering.py','gsplat/cuda/_backend.py')}}
    binary = metadata.distribution('gsplat').locate_file('gsplat/csrc.pyd')
    if binary.is_file():
        pin['windows_binary'] = {'platform':'win_amd64','architecture':'sm_86','bytes':binary.stat().st_size,
                                 'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    (ROOT/'third_party/gsplat-pin.json').write_text(json.dumps(pin,indent=2),'utf-8')
    distribution = metadata.distribution('ultralytics')
    for file in distribution.files or []:
        if Path(str(file)).name.upper() in ('LICENSE','LICENSE.TXT','LICENSE.MD'):
            shutil.copy2(distribution.locate_file(file), ROOT/'third_party/licenses/Ultralytics-LICENSE.txt')
            break
    audit = (ROOT/'environments/windows-runtime.freeze.audit.txt').read_text('utf-8-sig')
    lines = [line for line in audit.splitlines() if not line.lower().startswith('gsplat')]
    header = '# Windows实际完整依赖；gsplat需另按固定源码编译，不能安装无扩展占位包。\n--extra-index-url https://download.pytorch.org/whl/cu121\n'
    (ROOT/'environments/windows-runtime.lock.txt').write_text(header+'\n'.join(lines)+'\n','utf-8')
    print('许可、源码pin和Windows实际锁文件已保存')


if __name__ == '__main__':
    main()
