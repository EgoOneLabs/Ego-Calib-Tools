#!/usr/bin/env python3
"""Read-only diagnosis of a saved 2UQ2 IMU recording; never edits source files."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import numpy as np


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()


def inspect_counters(values):
    c=np.asarray(values,dtype=np.int64)
    if len(c)<2:raise ValueError('原始计数样本不足')
    delta=(np.diff(c))%(2**32)
    bad=np.flatnonzero(delta!=32)
    events=[]
    totals=collections.Counter()
    for pos in bad:
        old,new=int(c[pos]),int(c[pos+1]);step32=int(delta[pos]);step24=(new-old)%(2**24)
        wrap24=(old<2**24 and new<old and new<2**24 and old>=2**24-8192 and new<=8192 and 0<step24<=8192 and step24%32==0)
        if wrap24:
            kind='POSSIBLE_24BIT_WRAP';gap=step24//32-1
        elif step32==0:
            kind='DUPLICATE';gap=0
        elif 0<step32<2**31 and step32%32==0:
            kind='FORWARD_GAP';gap=step32//32-1
        else:
            kind='OTHER_DISCONTINUITY';gap=None
        totals[kind]+=1
        if gap is not None:totals['missing_if_24bit_wrap_hypothesis']+=gap
        events.append({'sample_index_after':int(pos+1),'packet_after':int((pos+1)//14+1),
            'counter_before':old,'counter_after':new,'counter_before_hex':hex(old),'counter_after_hex':hex(new),
            'delta_32bit':step32,'delta_24bit':step24,'classification':kind,
            'missing_if_24bit_wrap_hypothesis':gap})
    return {'samples':len(c),'counter_min':int(c.min()),'counter_max':int(c.max()),
            'counter_high_byte_always_zero':bool(np.all(c<2**24)),
            'event_counts':dict(totals),'events':events}


def diagnose(root):
    root=Path(root).resolve()
    binary=root/'imu_packets.bin';requests=root/'imu_requests.csv';meta=root/'imu_capture.json'
    for path in (binary,requests,meta):
        if not path.is_file():raise ValueError('找不到原始文件：'+str(path))
    if binary.stat().st_size%252:raise ValueError('原始包文件长度不是 252 的整数倍，停止')
    capture=json.loads(meta.read_text())
    dtype=np.dtype([('magic','S2'),('counter','>u4'),('axes','>i2',(6,))])
    data=np.fromfile(binary,dtype=dtype)
    if not np.all(data['magic']==b'\xde\xc8'):raise ValueError('原始文件存在非预期数据头，停止')
    result=inspect_counters(data['counter'])
    wanted={e['packet_after'] for e in result['events']}
    request_by_packet={};error_reasons=collections.Counter();examples=[]
    valid_packet=0;first=None;last=None
    with requests.open() as f:
        for row in csv.DictReader(f):
            if row.get('phase')!='record':continue
            if row.get('valid')=='True':
                valid_packet+=1
                if first is None:first=int(row['host_before_ns'])
                last=int(row['host_after_ns'])
                if valid_packet in wanted:
                    request_by_packet[valid_packet]={k:row[k] for k in ('request','host_before_ns','host_after_ns','unique_samples')}
            else:
                reason=row.get('error','');error_reasons[reason]+=1
                if len(examples)<30:examples.append(row)
    for e in result['events']:
        e['host_request_after']=request_by_packet.get(e['packet_after'])
    counts=result['event_counts']
    report={'status':'COUNTER_DIAGNOSTIC_ONLY','source_files_modified':False,
        'capture':capture,'valid_packets_from_requests':valid_packet,
        'raw_packets':binary.stat().st_size//252,'raw_sha256':sha(binary),
        'capture_json_sha256':sha(meta),'error_reasons':dict(error_reasons),
        'error_examples':examples,'counter_analysis':result,
        'clock_or_hardware_sync_confirmed':False}
    if first is not None and last>first and counts.get('OTHER_DISCONTINUITY',0)==0 and counts.get('DUPLICATE',0)==0:
        report['rate_if_24bit_wrap_hypothesis_hz']=(len(data)-1+counts.get('missing_if_24bit_wrap_hypothesis',0))/((last-first)/1e9)
    # All new files go into a fresh sibling directory. Original recording is read-only.
    out=Path(tempfile.mkdtemp(prefix='imu_counter_diagnostic_',dir=root.parent))
    (out/'counter_diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    with tarfile.open(out/'imu_counter_diagnostic.tar.gz','w:gz') as t:
        t.add(out/'counter_diagnostic.json',arcname='counter_diagnostic.json')
    print('诊断完成；原始采集文件未修改。')
    print('请上传：'+str(out/'imu_counter_diagnostic.tar.gz'))
    print('回绕候选：'+str(counts.get('POSSIBLE_24BIT_WRAP',0)))
    print('其他不连续：'+str(counts.get('OTHER_DISCONTINUITY',0)))
    subprocess.run(['xdg-open',str(out)],check=False)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path)
    try:diagnose(parser.parse_args().run)
    except Exception as e:raise SystemExit('诊断停止：'+str(e))
