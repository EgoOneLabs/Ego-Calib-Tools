"""Remember explicitly used/generated parameters per device, with content hashes."""
import json
import os
from pathlib import Path
import threading
from core import device_id, sha, require


class Parameters:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.RLock()

    def read(self):
        try:
            value=json.loads(self.path.read_text())
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}

    def remember(self,ident,kind,path):
        ident=device_id(ident);require(kind in ('camera','imu'),'未知参数类型')
        path=Path(path).resolve();require(path.is_file() and 0<path.stat().st_size<=32768,'参数文件缺失或过大')
        with self.lock:
            saved=self.read();saved.setdefault(ident,{})[kind]=dict(path=str(path),sha256=sha(path))
            self.path.parent.mkdir(parents=True,exist_ok=True)
            pending=self.path.with_suffix('.json.pending')
            pending.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n');os.replace(pending,self.path)

    def defaults(self,ident):
        ident=device_id(ident);result={}
        with self.lock:
            saved=self.read().get(ident,{})
            for kind in ('camera','imu'):
                entry=saved.get(kind,{})
                try:
                    path=Path(entry['path'])
                    if not path.is_file() or not 0<path.stat().st_size<=32768 or sha(path)!=entry['sha256']:continue
                    result[kind]=dict(name=path.name,path=str(path),text=path.read_text())
                except (OSError,KeyError,UnicodeError):continue
        return result
