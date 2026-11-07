#!/usr/bin/env python3
"""Archive the existing DS camera result without rerunning Kalibr or activating parameters."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / 'reference/2uq2-ds-20261102'
EXPECTED_SHA = '153ab87359e8efd07be55a3d5c4734911bfbd7b7277452eb91087c4976c97aaf'
FILES = ('camera_4hz-camchain.yaml', 'camera_4hz-report-cam.pdf', 'camera_4hz-results-cam.txt')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def load_yaml(text, container):
    try:
        import yaml
    except ImportError:
        require(shutil.which('docker'), 'Need PyYAML or the existing kalibr Docker container')
        info = json.loads(subprocess.run(['docker', 'inspect', container], check=True, capture_output=True, text=True).stdout)[0]
        if not info['State']['Running']:
            subprocess.run(['docker', 'start', container], check=True)
        code = 'import yaml,json,sys; print(json.dumps(yaml.safe_load(sys.stdin.read()),allow_nan=False))'
        result = subprocess.run(['docker', 'exec', '-i', container, 'python3', '-c', code],
                                input=text, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(result.returncode == 0, 'Container YAML parse failed: ' + result.stderr[-2000:])
        return json.loads(result.stdout)
    return yaml.safe_load(text)


def validate_chain(chain):
    require(isinstance(chain, dict) and set(chain) == {'cam0', 'cam1'}, 'Expected exactly cam0 and cam1')
    for eye in (0, 1):
        c = chain['cam%d' % eye]
        require(c['camera_model'] == 'ds' and c['distortion_model'] == 'none', 'Expected historical DS-none model')
        require(c['resolution'] == [1920, 1080], 'Historical resolution mismatch')
        require(c['rostopic'] == '/cam%d/image_raw' % eye, 'Camera topic ordering differs')
        require(c['distortion_coeffs'] == [], 'DS-none must have no distortion coefficients')
        values = c['intrinsics']
        require(len(values) == 6 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values), 'Invalid DS intrinsics')
        xi, alpha, fx, fy, cx, cy = values
        require(0 < alpha < 1 and fx > 0 and fy > 0, 'Invalid DS alpha or focal lengths')
    transform = chain['cam1']['T_cn_cnm1']
    require(len(transform) == 4 and all(len(row) == 4 for row in transform), 'Transform must be 4x4')
    require(all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for row in transform for v in row), 'Non-finite transform')
    require(all(abs(a-b) < 1e-10 for a, b in zip(transform[3], [0, 0, 0, 1])), 'Invalid homogeneous transform row')
    rot = [row[:3] for row in transform[:3]]
    error = max(abs(sum(rot[k][i] * rot[k][j] for k in range(3)) - (1 if i == j else 0))
                for i in range(3) for j in range(3))
    det = (rot[0][0] * (rot[1][1]*rot[2][2]-rot[1][2]*rot[2][1])
           - rot[0][1] * (rot[1][0]*rot[2][2]-rot[1][2]*rot[2][0])
           + rot[0][2] * (rot[1][0]*rot[2][1]-rot[1][1]*rot[2][0]))
    require(error < 1e-6 and abs(det - 1) < 1e-6, 'Rotation is not a proper orthonormal matrix')
    baseline = math.sqrt(sum(transform[i][3]**2 for i in range(3)))
    require(baseline > 0, 'Zero stereo baseline')
    return {'baseline_m': baseline, 'rotation_determinant': det,
            'rotation_orthogonality_max_abs_error': error,
            'note': 'Structural checks only; these values do not establish calibration quality.'}


def check_report_summary(text, chain):
    for eye in (0, 1):
        match = re.search(r'cam%d\s*\([^\n]+\):(.*?)(?=\ncam\d\s*\(|\nbaseline|\Z)' % eye, text, re.S)
        require(match is not None, 'Report is missing camera summary: cam%d' % eye)
        block = match.group(1)
        require('DoubleSphere' in block, 'Report model is not DS for cam%d; do not mix equi reports with DS YAML' % eye)
        projection = re.search(r'projection:\s*\[([^\]]+)\]', block, re.S)
        require(projection is not None, 'Report missing projection parameters')
        values = [float(v) for v in projection.group(1).split()]
        expected = chain['cam%d' % eye]['intrinsics']
        require(len(values) == len(expected) and all(abs(a-b) <= 1e-6 for a, b in zip(values, expected)), 'Report projection parameters differ from YAML')
    baseline = re.search(r'baseline\s+T_1_0:.*?\bt:\s*\[([^\]]+)\]', text, re.S)
    require(baseline is not None, 'Report missing stereo translation')
    translation = [float(v) for v in baseline.group(1).split()]
    expected = [chain['cam1']['T_cn_cnm1'][i][3] for i in range(3)]
    require(len(translation) == 3 and all(abs(a-b) <= 1e-6 for a, b in zip(translation, expected)), 'Report translation differs from YAML')


def pdf_summary(path):
    require(shutil.which('pdftotext'), 'Missing pdftotext; Ubuntu: sudo apt install poppler-utils')
    result = subprocess.run(['pdftotext', '-f', '1', '-l', '1', '-layout', str(path), '-'],
                            check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout


def import_result(source, output_root, expected_sha=EXPECTED_SHA, container='kalibr'):
    source = source.resolve()
    require(source.is_dir(), 'Existing DS result directory missing: ' + str(source))
    for name in FILES:
        require((source / name).is_file() and (source / name).stat().st_size > 0, 'Required result missing/empty: ' + str(source / name))
    before = {name: sha(source / name) for name in FILES}
    require(before[FILES[0]] == expected_sha, 'Camchain SHA256 differs from the known historical result; do not substitute another YAML')
    chain = load_yaml((source / FILES[0]).read_text(), container)
    geometry = validate_chain(chain)
    with (source / FILES[1]).open('rb') as pdf:
        require(pdf.read(5) == b'%PDF-', 'Report is not a PDF file')
    text = (source / FILES[2]).read_text()
    require(text.strip(), 'Empty text report')
    check_report_summary(text, chain)
    check_report_summary(pdf_summary(source / FILES[1]), chain)
    output_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='ds_existing_', dir=output_root)).resolve()
    copied = root / 'original_results'
    copied.mkdir()
    for name in FILES:
        shutil.copyfile(source / name, copied / name)
        require(sha(copied / name) == before[name] == sha(source / name), 'Source changed during snapshot: ' + name)
    profile = {'schema_version': 'ego_camera_profile_v1', 'profile_id': root.name,
               'status': 'EXISTING_CAMERA_RESULT_IMPORTED_REVIEW_PENDING',
               'imported_at_utc': datetime.now(timezone.utc).isoformat(),
               'source_directory': str(source), 'result_files': {
                   name: {'snapshot_file': 'original_results/' + name, 'sha256': before[name]} for name in FILES},
               'camera_order': ['left', 'right'], 'camera_parameters': chain, 'geometry_checks': geometry,
               'hardware_model': '2UQ2', 'hardware_unit_serial': None,
               'device_unit_association_verified': False,
               'quality_review_status': 'PENDING', 'calibration_quality_accepted': False,
               'calibration_rerun': False, 'activated_in_android_app': False,
               'camera_imu_extrinsics_included': False, 'hardware_sync_verified': False,
               'target_configuration_provenance': 'Not reconstructed from memory; confirm original target configuration in quality review.',
               'report_association': 'Both TXT and PDF first-page model, intrinsics and stereo translation match YAML within 1e-6; full report quality not automatically accepted.'}
    (root / 'camera_profile.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    (root / 'IMPORT_NOTES.zh-CN.md').write_text(
        '# 已有相机结果导入\n\n'
        '状态：已有结果已归档，质量待复核。没有重跑 Kalibr，没有覆盖旧参数，没有激活到安卓 App。\n\n'
        '原 DS YAML 摘要与已知基线一致；左右模型、分辨率、话题顺序和变换结构检查通过。\n\n'
        '双目基线：%.6f mm。此数值及其与粗测的接近不能代替质量验收。\n\n'
        '下一步复核原 PDF/TXT 的重投影误差、观测覆盖、标定板配置与设备对应关系。'
        '先保留 PENDING 状态，不自动替换正式参数。\n' % (geometry['baseline_m'] * 1000))
    archive = root / 'existing_camera_result_small_review.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in FILES:
            tar.add(copied / name, arcname='original_results/' + name)
        for name in ('camera_profile.json', 'IMPORT_NOTES.zh-CN.md'):
            tar.add(root / name, arcname=name)
    print('导入完成，质量待复核；没有运行标定。')
    print('输出目录：' + str(root))
    print('请上传：' + str(archive))
    return root


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    p.add_argument('--output-root', type=Path, required=True, help='Explicit local output parent; never write into bundled reference files')
    p.add_argument('--container', default='kalibr')
    a = p.parse_args()
    try:
        import_result(a.source, a.output_root, container=a.container)
    except Exception as e:
        sys.exit(str(e))
