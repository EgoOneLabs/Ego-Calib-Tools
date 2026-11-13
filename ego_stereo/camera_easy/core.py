"""Camera-only preparation and output checks. No ROS dependency on the host."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import numpy as np
import yaml

WIDTH, HEIGHT = 3840, 1080
EYE_WIDTH = WIDTH // 2
SAMPLE_HZ = 4.0

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

@dataclass(frozen=True)
class Board:
    rows: int = 6
    cols: int = 6
    tag_mm: float = 88.0
    gap_mm: float = 26.4

    @classmethod
    def parse(cls, value):
        rows, cols = float(value['rows']), float(value['cols'])
        tag, gap = float(value['tag_mm']), float(value['gap_mm'])
        require(all(math.isfinite(v) for v in (rows, cols, tag, gap)), '标定板参数必须是有限数值')
        require(rows.is_integer() and cols.is_integer() and 2 <= rows <= 30 and 2 <= cols <= 30, '行数、列数应为 2–30 的整数')
        require(1 <= tag <= 500 and 0 < gap < tag * 2, '请检查实测标签边长与空白间距，单位为 mm')
        return cls(int(rows), int(cols), tag, gap)

    def write(self, root):
        data = dict(target_type='aprilgrid', tagRows=self.rows, tagCols=self.cols,
                    tagSize=self.tag_mm / 1000, tagSpacing=self.gap_mm / self.tag_mm)
        Path(root, 'aprilgrid.yaml').write_text(yaml.safe_dump(data, sort_keys=False))
        Path(root, 'board_measurements.json').write_text(json.dumps(asdict(self), indent=2))
        return data

def device_id(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value),
            '设备编号请使用 1–64 位英文字母、数字、下划线或短横线')
    return value

class FrameStore:
    def __init__(self, root):
        self.root = Path(root)
        self.pairs = []
        for eye in ('cam0', 'cam1'):
            (self.root / 'images' / eye).mkdir(parents=True, exist_ok=False)

    def add(self, gray, stamp):
        require(gray.dtype == np.uint8 and gray.shape == (HEIGHT, WIDTH), '实际图像必须为 3840×1080 灰度；停止，未缩放图像')
        require(type(stamp) is int and (not self.pairs or stamp > self.pairs[-1]['timestamp_ns']), '帧时间必须严格递增')
        pair = {'timestamp_ns': stamp}
        header = f'P5\n{EYE_WIDTH} {HEIGHT}\n255\n'.encode()
        for index, side in enumerate(('left', 'right')):
            path = self.root / 'images' / f'cam{index}' / f'{stamp}.pgm'
            payload = header + gray[:, index * EYE_WIDTH:(index + 1) * EYE_WIDTH].tobytes()
            with path.open('xb') as stream:
                stream.write(payload)
            pair[side] = {'file': path.relative_to(self.root).as_posix(), 'sha256': hashlib.sha256(payload).hexdigest()}
        self.pairs.append(pair)

    def finish(self):
        require(len(self.pairs) >= 40, '图像少于 40 对，请重新采集；数量门槛不代表图案观测质量通过')
        manifest = dict(status='CAMERA_FRAMES_PREPARED', purpose='calibration',
                        width=EYE_WIDTH, height=HEIGHT, sample_hz=SAMPLE_HZ,
                        selected_pair_count=len(self.pairs), selected_pairs=self.pairs,
                        timestamp_semantics='Host complete-frame dequeue monotonic time mapped to Unix once; not exposure; camera only',
                        hardware_sync_verified=False, image_geometry_changed=False,
                        preprocessing='MJPEG decoded to mono8, split at x=1920; no resize, crop, rectification or sharpening; PGM lossless')
        (self.root / 'camera_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        return manifest

def inspect_outputs(root):
    root = Path(root)
    for name in ('camera-camchain.yaml', 'camera-results-cam.txt', 'camera-report-cam.pdf'):
        require((root / name).is_file() and (root / name).stat().st_size > 0, '缺少标定输出：' + name)
    require((root / 'camera-report-cam.pdf').read_bytes().startswith(b'%PDF-'), 'PDF 报告格式不正确')
    chain = yaml.safe_load((root / 'camera-camchain.yaml').read_text())
    for index in range(2):
        cam = chain[f'cam{index}']
        require(cam['camera_model'] == 'ds' and cam['distortion_model'] == 'none', '模型输出与 ds-none 不符')
        require(cam['resolution'] == [EYE_WIDTH, HEIGHT], '标定分辨率与输入不一致')
        require(cam['rostopic'] == f'/cam{index}/image_raw', '相机话题顺序不一致')
        intr = np.array(cam['intrinsics'], dtype=float)
        require(intr.shape == (6,) and np.isfinite(intr).all(), '内参为空或包含 NaN/Inf')
        require(0 < intr[1] < 1 and intr[2] > 0 and intr[3] > 0, 'DS 焦距或 alpha 无效')
    transform = np.array(chain['cam1']['T_cn_cnm1'], dtype=float)
    require(transform.shape == (4, 4) and np.isfinite(transform).all(), '双目外参无效')
    require(np.allclose(transform[3], [0, 0, 0, 1]), '外参最后一行无效')
    rot = transform[:3, :3]
    require(np.allclose(rot.T @ rot, np.eye(3), atol=1e-3) and abs(np.linalg.det(rot) - 1) < 1e-3, '旋转矩阵无效')
    baseline = float(np.linalg.norm(transform[:3, 3]) * 1000)
    require(baseline > 0, '双目基线为零')
    return {'status': 'OUTPUTS_COMPLETE_REVIEW_PENDING', 'stereo_baseline_mm': baseline,
            'finite_intrinsics_and_rigid_transform': True, 'quality_accepted': False,
            'files': {n: sha(root / n) for n in ('camera-camchain.yaml', 'camera-results-cam.txt', 'camera-report-cam.pdf')}}
