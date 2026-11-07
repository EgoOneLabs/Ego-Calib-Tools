#!/usr/bin/env python3
"""Prepare paired, full-resolution mono8 camera frames; never changes the source session."""
import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from check_session import require, sha, read_times


def choose(times, hz):
    period = int(Decimal(10**9) / Decimal(str(hz)))
    require(period > 0, 'Invalid sampling period')
    indices = []
    for i, t in enumerate(times):
        if not indices or t - times[indices[-1]] >= period:
            indices.append(i)
    return indices


def decode_selected(video, directory, selected, count, width, height, log):
    directory.mkdir()
    selected = set(selected)
    entries = {}
    size = width * height
    with log.open('wb') as errors:
        p = subprocess.Popen(['ffmpeg', '-v', 'error', '-xerror', '-err_detect', 'explode',
                              '-threads', '1', '-i', str(video), '-map', '0:v:0', '-an',
                              '-vsync', '0', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'],
                             stdout=subprocess.PIPE, stderr=errors)
        try:
            for i in range(count):
                data = p.stdout.read(size)
                require(len(data) == size, 'Video ended before expected frame ' + str(i))
                if i in selected:
                    image = directory / ('%08d.pgm' % i)
                    image.write_bytes(('P5\n%d %d\n255\n' % (width, height)).encode() + data)
                    entries[i] = {'file': str(image.relative_to(directory.parent)), 'sha256': sha(image)}
            require(not p.stdout.read(1), 'Video has more frames than metadata')
            code = p.wait()
            require(code == 0, 'FFmpeg decoding failed; inspect ' + str(log))
        finally:
            p.stdout.close()
            if p.poll() is None:
                p.kill()
                p.wait()
    require(log.stat().st_size == 0, 'FFmpeg reported an error; inspect ' + str(log))
    return entries


def prepare(session, report_path, output_root, purpose, hz):
    require(shutil.which('ffmpeg'), 'Missing ffmpeg')
    require(Decimal(str(hz)).is_finite() and 0 < hz <= 30, 'sample-hz must be >0 and <=30')
    session = session.resolve()
    report = json.loads(report_path.read_text())
    meta = json.loads((session / 'meta.json').read_text())
    require(report.get('status') == 'MEDIA_READBACK_PASS', 'A successful media_check.json is required')
    require(report['source_meta_sha256'] == sha(session / 'meta.json'), 'Metadata differs from verified report')
    require(meta.get('video_export_status') == 'COMPLETE', 'Video export not complete')
    if purpose == 'calibration':
        require(not str(meta.get('task', '')).startswith('app_export_unplug'), 'Unplug smoke recording cannot be used for calibration')
    for side in ('left', 'right'):
        require(report['videos'][side]['sha256'] == sha(session / 'videos' / (side + '.mkv')), 'Video differs from verified report: ' + side)
    times = read_times(session / 'timestamps/left_timestamps.txt')
    require(times == read_times(session / 'timestamps/right_timestamps.txt'), 'Stereo timestamp mismatch')
    with (session / 'export_video_index.csv').open() as f:
        index = list(csv.DictReader(f))
    require(len(index) == len(times) == meta['synced_frames'], 'Frame count mismatch')
    for side in ('left', 'right'):
        require(len(times) == meta['topics'][side]['written_frames'] == report['videos'][side]['frames'], 'Metadata count mismatch')
    for i, row in enumerate(index):
        require(int(row['output_frame_index']) == i, 'Non-contiguous export index')
        require(times[i] - times[0] == int(row['frame_receive_boottime_ns']) - int(index[0]['frame_receive_boottime_ns']), 'Time mapping mismatch')
    selected = choose(times, hz)
    require(len(selected) >= 2, 'Too few selected image pairs')
    output_root.mkdir(parents=True, exist_ok=True)
    geometry = [(meta['topics'][side]['width'], meta['topics'][side]['height']) for side in ('left', 'right')]
    require(geometry[0] == geometry[1], 'Different eye geometry')
    width, height = geometry[0]
    require(isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0, 'Invalid image geometry')
    # Space for full-resolution PGM pairs, uncompressed BAG, and margin.
    needed = len(selected) * width * height * 4 + 512 * 1024**2
    require(shutil.disk_usage(output_root).free >= needed, 'Insufficient free space: need approximately %.2f GiB' % (needed / 1024**3))
    run = Path(tempfile.mkdtemp(prefix='camera_' + purpose + '_', dir=output_root)).resolve()
    result = {'status': 'FAILED', 'purpose': purpose, 'source_session': str(session), 'calibration_passed': False}
    try:
        views = {}
        for side in ('left', 'right'):
            print('Decode and select:', side, flush=True)
            views[side] = decode_selected(session / 'videos' / (side + '.mkv'), run / side,
                                          selected, len(times), width, height, run / (side + '_decode.log'))
        pairs = [{'source_output_frame_index': i, 'timestamp_ns': times[i],
                  'source_frame_index': int(index[i]['source_frame_index']),
                  'uvc_sequence': int(index[i]['uvc_sequence']),
                  'left': views['left'][i], 'right': views['right'][i]} for i in selected]
        shutil.copyfile(report_path, run / 'source_media_check.json')
        shutil.copyfile(session / 'meta.json', run / 'source_meta.json')
        result.update(status='CAMERA_FRAMES_PREPARED', sample_hz_limit=hz,
                      sampling_policy='keep first pair then next actual timestamp >= last selected + 1/hz; no interpolation',
                      source_meta_sha256=sha(session / 'meta.json'), source_frames_per_eye=len(times),
                      width=width, height=height, encoding='mono8', timestamp_semantics=meta.get('video_timestamp_source'),
                      selected_pairs=pairs, selected_pair_count=len(pairs), imu_included=False,
                      calibration_input_quality_verified=False)
    except Exception as e:
        result['error'] = str(e)
        raise
    finally:
        (run / 'camera_manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print('输出目录：' + str(run), flush=True)
    return run


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--media-report', type=Path, required=True)
    p.add_argument('--output-root', type=Path, required=True, help='Explicit local output parent')
    p.add_argument('--purpose', choices=['smoke', 'calibration'], required=True)
    p.add_argument('--sample-hz', type=float, default=4.0)
    a = p.parse_args()
    try:
        prepare(a.session, a.media_report, a.output_root, a.purpose, a.sample_hz)
    except Exception as e:
        sys.exit(str(e))
