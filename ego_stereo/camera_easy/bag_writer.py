#!/usr/bin/env python3
"""Write camera-only ROS1 BAG, then independently read every image back."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024**2), b''):
            h.update(data)
    return h.hexdigest()


def pixels(root, item, width, height):
    path = (root / item['file']).resolve()
    require(root.resolve() in path.parents, 'Image path outside run directory')
    require(sha(path) == item['sha256'], 'Prepared image checksum mismatch')
    data = path.read_bytes()
    header = ('P5\n%d %d\n255\n' % (width, height)).encode()
    require(data.startswith(header) and len(data) == len(header) + width * height, 'Invalid PGM geometry or payload')
    return data[len(header):]


class Backend:
    def __init__(self, kind):
        self.kind = kind
        if kind == 'rosbag':
            import rosbag
            import rospy
            from sensor_msgs.msg import Image
            self.rb, self.rp, self.Image = rosbag, rospy, Image
        else:
            from rosbags.typesys import Stores, get_typestore
            self.store = get_typestore(Stores.ROS1_NOETIC)

    def write(self, path, root, manifest, expected):
        width, height = manifest['width'], manifest['height']
        if self.kind == 'rosbag':
            writer = self.rb.Bag(str(path), 'w')
        else:
            from rosbags.rosbag1 import Writer
            writer = Writer(path)
            writer.open()
            connections = {side: writer.add_connection('/cam%d/image_raw' % eye, 'sensor_msgs/msg/Image', typestore=self.store)
                           for eye, side in enumerate(('left', 'right'))}
        try:
            for seq, pair in enumerate(manifest['selected_pairs']):
                n = pair['timestamp_ns']
                sec, ns = divmod(n, 10**9)
                require(0 <= sec <= 0xffffffff and 0 <= ns < 10**9, 'Timestamp outside ROS1 range')
                for eye, side in enumerate(('left', 'right')):
                    topic = '/cam%d/image_raw' % eye
                    data = pixels(root, pair[side], width, height)
                    expected[(topic, n)] = (seq, hashlib.sha256(data).hexdigest(), 'cam%d' % eye)
                    if self.kind == 'rosbag':
                        stamp = self.rp.Time(sec, ns)
                        m = self.Image()
                        m.header.seq, m.header.stamp, m.header.frame_id = seq, stamp, 'cam%d' % eye
                        m.width, m.height, m.step, m.encoding, m.is_bigendian, m.data = width, height, width, 'mono8', 0, data
                        writer.write(topic, m, stamp)
                    else:
                        import numpy as np
                        t = self.store.types
                        stamp = t['builtin_interfaces/msg/Time'](sec, ns)
                        header = t['std_msgs/msg/Header'](seq, stamp, 'cam%d' % eye)
                        m = t['sensor_msgs/msg/Image'](header, height, width, 'mono8', 0, width, np.frombuffer(data, dtype=np.uint8))
                        c = connections[side]
                        writer.write(c, n, self.store.serialize_ros1(m, c.msgtype))
        finally:
            writer.close()

    def read(self, path):
        if self.kind == 'rosbag':
            with self.rb.Bag(str(path)) as reader:
                for topic, msg, time in reader.read_messages():
                    yield topic, time.to_nsec(), msg, msg.header.stamp.to_nsec()
        else:
            from rosbags.rosbag1 import Reader
            with Reader(path) as reader:
                for c, n, data in reader.messages():
                    m = self.store.deserialize_ros1(data, c.msgtype)
                    yield c.topic, n, m, m.header.stamp.sec * 10**9 + m.header.stamp.nanosec


def write(root, backend):
    manifest = json.loads((root / 'camera_manifest.json').read_text())
    require(manifest.get('status') == 'CAMERA_FRAMES_PREPARED', 'Preparation not complete')
    pairs = manifest['selected_pairs']
    require(len(pairs) == manifest['selected_pair_count'] and len(pairs) >= 2, 'Invalid selected pair count')
    require(all(b['timestamp_ns'] > a['timestamp_ns'] for a, b in zip(pairs, pairs[1:])), 'Non-increasing frame times')
    path = root / 'camera.bag'
    require(not path.exists() and not (root / 'bag_verification.json').exists(), 'BAG or verification already exists; use a new prepared run')
    bag = Backend(backend)
    result = {'status': 'FAILED', 'backend': backend, 'calibration_passed': False}
    try:
        expected = {}
        bag.write(path, root, manifest, expected)
        seen, counts = set(), {}
        for topic, n, m, stamp in bag.read(path):
            key = topic, n
            require(key in expected and key not in seen, 'Unexpected/duplicate BAG message')
            seq, digest, frame = expected[key]
            require(n == stamp and seq == m.header.seq and frame == m.header.frame_id, 'BAG timestamp/header mismatch')
            require((m.width, m.height, m.step, m.encoding, m.is_bigendian) ==
                    (manifest['width'], manifest['height'], manifest['width'], 'mono8', 0), 'BAG image geometry/encoding mismatch')
            require(hashlib.sha256(bytes(m.data)).hexdigest() == digest, 'BAG decoded pixel mismatch')
            seen.add(key)
            counts[topic] = counts.get(topic, 0) + 1
        require(seen == set(expected) and len(seen) == len(pairs) * 2, 'Missing BAG messages')
        result.update(status='CAMERA_BAG_READBACK_PASS', counts=counts, all_pixels_verified=True,
                      all_header_and_bag_timestamps_verified=True, bag_sha256=sha(path),
                      manifest_sha256=sha(root / 'camera_manifest.json'), imu_included=False,
                      timestamp_semantics=manifest.get('timestamp_semantics'))
    except Exception as e:
        result['error'] = str(e)
        raise
    finally:
        (root / 'bag_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--backend', choices=['rosbag', 'rosbags'], default='rosbag')
    a = p.parse_args()
    try:
        write(a.root.resolve(), a.backend)
    except Exception as e:
        sys.exit(str(e))
