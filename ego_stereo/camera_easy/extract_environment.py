"""Reuse only the verified environment archive from the published v1 full ZIP."""
import hashlib
from pathlib import Path
import re
import shutil
import sys
import tarfile
import zipfile


def extract(package, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package) as z:
        with z.open('camera.run') as stream:
            header = bytearray()
            while True:
                line = stream.readline()
                if not line or len(header) > 65536:
                    raise ValueError('完整包入口格式不正确')
                header.extend(line)
                if line == b'__EGO_PAYLOAD_BELOW__\n':
                    break
            expected = re.search(rb'== "([0-9a-f]{64})"', header)
            if not expected:
                raise ValueError('缺少完整包内容校验值')
            digest = hashlib.sha256()
            while data := stream.read(1024 * 1024):
                digest.update(data)
            if digest.hexdigest().encode() != expected[1]:
                raise ValueError('完整包内容校验失败')
        with z.open('camera.run') as stream:
            stream.read(len(header))
            with tarfile.open(fileobj=stream, mode='r|gz') as tar:
                for member in tar:
                    if member.name == 'environment/kalibr-environment.tar.gz':
                        if not member.isfile() or member.size <= 0:
                            raise ValueError('环境包类型不正确')
                        if shutil.disk_usage(destination.parent).free < member.size + 512 * 1024**2:
                            raise ValueError('提取环境镜像空间不足，请腾出磁盘空间')
                        pending = destination.with_suffix('.partial')
                        try:
                            with tar.extractfile(member) as src, pending.open('wb') as dst:
                                shutil.copyfileobj(src, dst, 1024 * 1024)
                            if pending.stat().st_size != member.size:
                                raise ValueError('环境镜像提取不完整')
                            pending.replace(destination)
                        finally:
                            pending.unlink(missing_ok=True)
                        return
    raise ValueError('完整包中缺少 Kalibr 环境镜像')


if __name__ == '__main__':
    extract(*sys.argv[1:])
