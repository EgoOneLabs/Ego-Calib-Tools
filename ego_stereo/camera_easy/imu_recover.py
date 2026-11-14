"""Reanalyze saved raw packets after empirically confirmed u24 counter rollover."""
import argparse
import csv
import json
from pathlib import Path
import tempfile
from collections import Counter

import numpy as np
from imu_capture import SCALE_ACC,SCALE_GYRO
from imu_analysis import analyze
from core import sha


def replay_counters(counters):
    c=np.asarray(counters,dtype=np.int64)
    if len(c)<100:raise ValueError('有效原始样本不足')
    delta=np.diff(c)%(2**32)
    short=np.diff(c)%(2**24)
    wrap=(c[:-1]>=2**24-8192)&(c[:-1]<2**24)&(c[1:]>=0)&(c[1:]<=8192)&(c[1:]<c[:-1])&(short>0)&(short<=8192)&(short%32==0)
    delta[wrap]=short[wrap]
    if np.any(delta<=0) or np.any(delta>=2**31) or np.any(delta%32):
        raise ValueError('原始数据仍有无法解释的重复或跳变，停止复算，不强行连接')
    tick=np.r_[0,np.cumsum(delta//32)]
    segment=np.r_[0,np.cumsum(delta!=32)]
    return tick,segment,{'counter_wraps_24bit':int(wrap.sum()),'counter_discontinuities':0,
                         'gaps':int(np.sum(delta!=32)),'missing_estimated':int(np.sum(delta//32-1))}


def recover(source,expected=None,notify=print):
    source=Path(source).resolve()
    for name in ('imu_packets.bin','imu_requests.csv','imu_capture.json'):
        if not (source/name).is_file():raise ValueError('找不到原始文件：'+name)
    notify('正在校验本次原始文件…')
    digests={n:sha(source/n) for n in ('imu_packets.bin','imu_requests.csv','imu_capture.json')}
    if expected:
        for name,digest in expected.items():
            if digests.get(name)!=digest:raise ValueError('复算包与原始文件不匹配：'+name)
    original=json.loads((source/'imu_capture.json').read_text())
    if original.get('duplicates')!=0:raise ValueError('本次工具要求原始记录无重复；请先诊断重复数据')
    dtype=np.dtype([('magic','S2'),('counter','>u4'),('axes','>i2',(6,))])
    if (source/'imu_packets.bin').stat().st_size%252:raise ValueError('原始包长度不完整')
    raw=np.fromfile(source/'imu_packets.bin',dtype=dtype)
    if not np.all(raw['magic']==b'\xde\xc8'):raise ValueError('有效包文件的数据头不匹配')
    if len(raw)!=original['samples']:raise ValueError('原始包样本数与采集统计不匹配')
    notify('正在按原始计数值重建连续片段，真实缺口不补点…')
    tick,segment,corrected=replay_counters(raw['counter'])
    times=[];errors=Counter()
    with (source/'imu_requests.csv').open() as f:
        for row in csv.DictReader(f):
            if row.get('phase')=='record' and row.get('valid')=='True':
                if int(row['unique_samples'])!=14:raise ValueError('原始有效请求不是 14 个唯一样本，停止复算')
                times.append(int(row['host_after_ns']))
            elif row.get('phase')=='record':errors[row.get('error','unknown')]+=1
    if len(times)*14!=len(raw):raise ValueError('主机请求记录与有效包数量不匹配')
    if np.any(np.diff(np.asarray(times,dtype=np.int64))<=0):raise ValueError('主机请求时间不递增')
    data=np.empty((len(raw),9),dtype=np.float64)
    data[:,0]=segment;data[:,1]=tick;data[:,2]=np.repeat(times,14)
    data[:,3:6]=raw['axes'][:,:3]*SCALE_ACC
    data[:,6:9]=raw['axes'][:,3:]*SCALE_GYRO
    del raw,tick,segment
    out=Path(tempfile.mkdtemp(prefix='imu_reanalysis_',dir=source.parent))
    (out/'original_imu_capture.json').write_text(json.dumps(original,ensure_ascii=False,indent=2)+'\n')
    metadata=dict(original);metadata.update(corrected)
    metadata['derivation']='Reanalysis of saved valid raw packets; original files unchanged; empirical u24 rollover interpretation.'
    metadata['original_counter_discontinuities']=original['counter_discontinuities']
    metadata['original_read_errors']=original['errors']
    metadata['original_error_reasons']=dict(errors)
    metadata['estimated_missing_fraction']=corrected['missing_estimated']/(len(data)+corrected['missing_estimated'])
    (out/'imu_capture.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    (out/'recovery.json').write_text(json.dumps({'status':'RAW_COUNTERS_REPLAYED','source_files_modified':False,
        'source_sha256':digests,'corrected_counts':corrected,'counter_unit_confirmed':False,
        'missing_samples_interpolated':False,'samples_restored_from_rejected_packets':0,
        'notes':'Previously rejected packets are absent from the valid raw file; no samples are invented.'},ensure_ascii=False,indent=2)+'\n')
    notify('正在生成 Allan 曲线、摘要和检查包…')
    try:
        report=analyze(out,notify=lambda stage,msg:notify(msg),prepared_data=data)
    except Exception as error:
        (out/'recovery_error.txt').write_text(str(error),encoding='utf-8');raise
    notify('复算完成。输出：'+str(out))
    notify('请上传：'+str(out/'imu_small_review.tar.gz'))
    return out,report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path)
    args=p.parse_args()
    expected_file=Path(__file__).with_name('expected_source.json')
    expected=json.loads(expected_file.read_text()) if expected_file.is_file() else None
    out,report=recover(args.source,expected)
    import subprocess
    subprocess.run(['xdg-open',str(out)],check=False)
