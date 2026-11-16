"""2UQ2 UVC XU capture. Raw counters are retained without inventing sample times."""
import csv
import ctypes
import fcntl
import json
import math
import os
from pathlib import Path
import struct
import time
from collections import deque

PACKET_BYTES = 252
COUNTER_STEP = 32
SCALE_ACC = 9.80665 / 4096
SCALE_GYRO = math.pi / 180 / 16.4


def counter_delta(before,after):
    """Accept the u24 boundary observed in this 2UQ2, retaining real resets.

    The stored field is still the original big-endian u32. This is an empirical
    rollover interpretation, not confirmation of counter tick duration.
    """
    delta=(after-before)%2**32
    short=(after-before)%2**24
    wrapped24=(2**24-8192<=before<2**24 and 0<=after<=8192 and after<before
               and 0<short<=8192 and short%COUNTER_STEP==0)
    return (short,True) if wrapped24 else (delta,False)


def decode_packet(raw):
    if len(raw) != PACKET_BYTES:
        raise ValueError('IMU 包长度不是 252 字节')
    rows=[]
    for offset in range(0, PACKET_BYTES, 18):
        magic,counter,*axes=struct.unpack_from('>2sI6h',raw,offset)
        if magic != b'\xde\xc8':
            raise ValueError('IMU 数据头不匹配')
        if rows and counter_delta(rows[-1][0],counter)[0] != COUNTER_STEP:
            raise ValueError('IMU 包内计数步长不是 32')
        rows.append((counter,*axes))
    return rows


class Query(ctypes.Structure):
    _fields_=[('unit',ctypes.c_uint8),('selector',ctypes.c_uint8),
              ('query',ctypes.c_uint8),('size',ctypes.c_uint16),
              ('data',ctypes.POINTER(ctypes.c_uint8))]


class XuReader:
    def __init__(self,device):
        self.fd=os.open(device,os.O_RDWR|os.O_CLOEXEC)
    def read(self):
        data=(ctypes.c_uint8*PACKET_BYTES)()
        query=Query(3,1,0x81,PACKET_BYTES,data)
        code=(3<<30)|(ctypes.sizeof(Query)<<16)|(ord('u')<<8)|0x21
        before=time.monotonic_ns()
        fcntl.ioctl(self.fd,code,bytearray(bytes(query)),True)
        after=time.monotonic_ns()
        return bytes(data),before,after
    def close(self):
        os.close(self.fd)


class Continuity:
    def __init__(self):
        self.last=None;self.segment=0;self.tick=0
        self.seen=set();self.queue=deque()
        self.duplicates=0;self.gaps=0;self.missing_estimated=0;self.resets=0
        self.wraps24=0
    def accept(self,counter):
        if counter in self.seen:
            self.duplicates+=1;return None
        if self.last is not None:
            delta,wrapped24=counter_delta(self.last,counter)
            if wrapped24:self.wraps24+=1
            if delta==COUNTER_STEP:self.tick+=1
            elif 0<delta<2**31 and delta%COUNTER_STEP==0:
                self.segment+=1;self.gaps+=1
                self.missing_estimated+=delta//COUNTER_STEP-1
                self.tick+=delta//COUNTER_STEP
            else:
                self.segment+=1;self.resets+=1;self.tick+=1
        self.last=counter;self.seen.add(counter);self.queue.append(counter)
        if len(self.queue)>4096:self.seen.remove(self.queue.popleft())
        return self.segment,self.tick


def capture(run,device,seconds,stop,finish,notify,reader_factory=XuReader,poll_wait_seconds=.01):
    if not math.isfinite(poll_wait_seconds) or not 0 <= poll_wait_seconds <= .1:
        raise ValueError("IMU 读取后等待必须在 0～0.1 秒之间")
    run=Path(run); c=Continuity();count=0;packets=0;errors=0;consecutive=0
    reader=None;completed=False;error=None
    record_start=time.monotonic()
    stats={'status':'RUNNING','quality_accepted':False,'requested_seconds':seconds,'poll_wait_seconds':poll_wait_seconds,
           'timestamp_semantics':'Host request interval is packet timing only; raw counter unit and exposure relation are not vendor-confirmed. No per-sample timestamps invented.',
           'nominal_scale':{'accel_counts_per_g':4096,'gyro_counts_per_deg_s':16.4,'per_unit_calibrated':False}}
    (run/'imu_capture.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
    try:
        reader=reader_factory(device)
        with (run/'imu_packets.bin').open('wb') as binary, (run/'imu_rejected_packets.bin').open('wb') as rejected, (run/'imu_requests.csv').open('w',newline='') as requests, (run/'imu_samples.csv').open('w',newline='') as samples:
            rw=csv.writer(requests);sw=csv.writer(samples)
            rw.writerow(['request','host_before_ns','host_after_ns','phase','bytes','valid','unique_samples','error','rejected_offset'])
            sw.writerow(['segment','tick_index','counter_raw','packet','host_before_ns','host_after_ns','ax_raw','ay_raw','az_raw','gx_raw','gy_raw','gz_raw','ax_m_s2','ay_m_s2','az_m_s2','gx_rad_s','gy_rad_s','gz_rad_s'])
            last_flush=time.monotonic();last_notify=0
            while not stop.is_set():
                now=time.monotonic()
                if record_start is not None and now-record_start>=seconds:
                    completed=True;break
                if finish.is_set():break
                before=time.monotonic_ns();after=before;raw=b''
                try:
                    raw,before,after=reader.read()
                    rows=decode_packet(raw);consecutive=0
                    added=0
                    binary.write(raw);packets+=1
                    for counter,*axes in rows:
                        accepted=c.accept(counter)
                        if accepted is None:continue
                        segment,tick=accepted
                        sw.writerow([segment,tick,counter,packets,before,after,*axes,
                            *[a*SCALE_ACC for a in axes[:3]],*[g*SCALE_GYRO for g in axes[3:]]])
                        count+=1;added+=1
                    rw.writerow([stats.get('requests',0),before,after,'record',len(raw),True,added,'',''])
                except (OSError,ValueError) as e:
                    errors+=1;consecutive+=1
                    offset=rejected.tell() if raw else ''
                    if raw:rejected.write(raw)
                    rw.writerow([stats.get('requests',0),before,time.monotonic_ns(),'record',len(raw),False,0,str(e),offset])
                    if consecutive>=20:raise ValueError('IMU 连续 20 次读取失败：'+str(e)) from e
                stats['requests']=stats.get('requests',0)+1
                now=time.monotonic()
                if now-last_notify>=.5:
                    notify('IMU_RECORDING',
                        {'samples':count,'packets':packets,'errors':errors,'gaps':c.gaps,
                         'duplicates':c.duplicates,'elapsed':0 if record_start is None else round(now-record_start,1)})
                    last_notify=now
                if now-last_flush>=2:
                    for f in (binary,rejected,requests,samples):f.flush()
                    last_flush=now
                    if os.statvfs(run).f_bavail*os.statvfs(run).f_frsize<256*1024**2:
                        raise ValueError('磁盘剩余空间不足，IMU 录制已停止，已有数据保留')
                # Default is unchanged. Zero wait is an explicit diagnostic option.
                stop.wait(poll_wait_seconds)
    except Exception as e:
        error=str(e);raise
    finally:
        if reader is not None:
            try:reader.close()
            except OSError as e:stats['close_error']=str(e)
        elapsed=0 if record_start is None else time.monotonic()-record_start
        stats.update(status='CAPTURE_COMPLETED' if completed else 'CAPTURE_ABORTED' if stop.is_set() or error else 'CAPTURE_STOPPED_EARLY',
            samples=count,packets=packets,errors=errors,elapsed_seconds=elapsed,
            duplicates=c.duplicates,gaps=c.gaps,missing_estimated=c.missing_estimated,
            counter_discontinuities=c.resets,counter_wraps_24bit=c.wraps24,
            counter_rollover_basis='Observed 2UQ2 u24 boundary inside a u32 field; tick time not vendor-confirmed',error=error)
        (run/'imu_capture.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
    if count<100:raise ValueError('有效 IMU 样本不足，已有原始文件保留')
    return stats
