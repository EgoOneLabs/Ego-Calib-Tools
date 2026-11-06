#!/usr/bin/env python3
"""Read-only validation of Android code11 stereo exports. No calibration acceptance."""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def run(argv):
    p = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(p.returncode == 0, 'Command failed: ' + repr(argv) + '\n' + p.stderr[-5000:])
    # ffmpeg can log a decoder error while still returning zero.
    require(not p.stderr.strip(), 'Decoder/probe reported an error:\n' + p.stderr[-5000:])
    return p.stdout


def read_times(path):
    times = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        fields = re.split(r'[\s,]+', line.strip())
        require(len(fields) == 2, 'Expected frame_index,timestamp (seconds or integer ns): ' + str(path))
        require(int(fields[0]) == len(times), 'Non-contiguous zero-based timestamp frame index')
        value = Decimal(fields[1])
        require(value.is_finite() and value > 0, 'Invalid timestamp')
        # Explicit epoch ranges: no silent milliseconds/microseconds guessing.
        if Decimal('1e8') <= value < Decimal('1e11'):
            value *= 10**9
        else:
            require(Decimal('1e17') <= value < Decimal('1e20'), 'Unsupported timestamp units')
        require(value == value.to_integral_value(), 'Sub-nanosecond timestamp')
        times.append(int(value))
    require(times and all(b > a for a, b in zip(times, times[1:])), 'Empty or non-increasing timestamps')
    return times


def video(path, timestamps, expected, out):
    probe = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                            '-show_streams', '-show_frames', '-show_entries',
                            'stream=codec_name,width,height:frame=best_effort_timestamp_time',
                            '-of', 'json', str(path)]))
    streams = probe.get('streams', [])
    require(len(streams) == 1, 'Expected one video stream: ' + str(path))
    stream = streams[0]
    require(stream.get('codec_name') == 'mjpeg', 'Expected lossless-split MJPEG stream')
    require((stream['width'], stream['height']) == (expected['width'], expected['height']), 'Video geometry mismatch')
    frames = probe.get('frames', [])
    require(len(frames) == len(timestamps) == expected['written_frames'], 'Video/timestamp/metadata frame count mismatch')
    pts = [Decimal(f['best_effort_timestamp_time']) for f in frames]
    require(all(b > a for a, b in zip(pts, pts[1:])), 'Non-increasing MKV timestamps')
    errors = [abs((p - pts[0]) * 10**9 - (t - timestamps[0])) for p, t in zip(pts, timestamps)]
    require(max(errors) <= 1000000, 'MKV timing differs from timestamp file by over 1 ms')
    decoded = run(['ffmpeg', '-v', 'error', '-xerror', '-err_detect', 'explode',
                   '-threads', '1', '-i', str(path), '-map', '0:v:0', '-an',
                   '-vsync', '0', '-f', 'framemd5', '-'])
    hashes = [line for line in decoded.splitlines() if line and not line.startswith('#')]
    require(len(hashes) == len(timestamps), 'Full-decode frame count mismatch')
    (out / (path.stem + '_decoded.framemd5')).write_text(decoded)
    return dict(frames=len(frames), width=stream['width'], height=stream['height'],
                max_relative_pts_error_ns=int(max(errors)), sha256=sha(path), full_decode=True)


def check(session, out, report):
    meta = json.loads((session / 'meta.json').read_text())
    require(meta.get('video_export_status') == 'COMPLETE', 'Video export metadata is not COMPLETE')
    times = {side: read_times(session / 'timestamps' / (side + '_timestamps.txt')) for side in ('left', 'right')}
    require(times['left'] == times['right'], 'Left/right timestamps are different')
    with (session / 'export_video_index.csv').open() as f:
        index = list(csv.DictReader(f))
    require(len(index) == len(times['left']) == meta['synced_frames'], 'Export index count mismatch')
    boots = [int(r['frame_receive_boottime_ns']) for r in index]
    for i, row in enumerate(index):
        require(int(row['output_frame_index']) == i, 'Export index not contiguous')
        require(times['left'][i] - times['left'][0] == boots[i] - boots[0], 'Timestamp/export index relative mapping mismatch')
    for key in ('source_list_position', 'source_frame_index'):
        values = [int(r[key]) for r in index]
        require(all(b > a for a, b in zip(values, values[1:])), 'Non-increasing source index: ' + key)
    anchor = meta.get('audio', {})
    if 'episode_anchor_boottime_ns' in anchor and 'episode_anchor_unix_ms' in anchor:
        require(all(t == anchor['episode_anchor_unix_ms'] * 1000000 + b - anchor['episode_anchor_boottime_ns']
                    for t, b in zip(times['left'], boots)), 'Absolute anchor mapping mismatch')
        report['absolute_anchor_mapping_checked'] = True
    else:
        report['absolute_anchor_mapping_checked'] = False
    report['videos'] = {}
    for side in ('left', 'right'):
        print('Full decoding:', side, flush=True)
        report['videos'][side] = video(session / 'videos' / (side + '.mkv'), times[side], meta['topics'][side], out)
    # Audio is inspected separately; absent audio does not invalidate camera-only input.
    audio = meta.get('audio', {})
    if meta.get('audio_requested') or meta.get('audio_enabled'):
        require(audio.get('status') == 'COMPLETE', 'Audio export incomplete')
        rel = Path(audio.get('wav_file', 'audio/audio.wav'))
        require(not rel.is_absolute() and '..' not in rel.parts, 'Unsafe WAV relative path')
        path = session / rel
        with wave.open(str(path), 'rb') as wav:
            require(wav.getcomptype() == 'NONE', 'Expected PCM WAV')
            require((wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) ==
                    (audio['sample_rate_hz'], audio['channels'], audio['bits_per_sample'] // 8, audio['frames']), 'WAV header/metadata mismatch')
            count = 0
            nonzero = False
            while True:
                block = wav.readframes(65536)
                if not block:
                    break
                count += len(block)
                nonzero |= any(block)
            require(count == audio['pcm_bytes'] == audio['frames'] * audio['channels'] * (audio['bits_per_sample'] // 8), 'Truncated WAV or PCM count mismatch')
            require(abs(audio['duration_sec'] - wav.getnframes() / wav.getframerate()) < 1e-6, 'WAV duration mismatch')
        run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-map', '0:a:0', '-f', 'null', '-'])
        report['audio'] = dict(full_decode=True, pcm_bytes=count, nonzero=nonzero, sha256=sha(path))
    else:
        report['audio'] = {'status': 'NOT_REQUESTED'}
    gaps = [b-a for a, b in zip(times['left'], times['left'][1:])]
    report.update(status='MEDIA_READBACK_PASS', frames_per_eye=len(index),
                  max_camera_frame_interval_ms=max(gaps, default=0) / 1e6,
                  source_meta_sha256=sha(session / 'meta.json'),
                  timestamp_source=meta.get('video_timestamp_source'),
                  calibration_passed=False, target_coverage_checked=False, hardware_sync_verified=False,
                  note='File integrity only; does not certify calibration image quality or IMU continuity.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True, help='New output directory; existing directories rejected')
    a = p.parse_args()
    for tool in ('ffmpeg', 'ffprobe'):
        require(shutil.which(tool), 'Missing dependency: ' + tool)
    a.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAILED', 'session': str(a.session.resolve())}
    try:
        check(a.session, a.output, report)
    except Exception as e:
        report.update(status='FAILED', error=str(e))
        print(str(e), file=sys.stderr)
    (a.output / 'media_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'MEDIA_READBACK_PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
