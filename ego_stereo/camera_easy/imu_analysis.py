"""Overlapping Allan deviation over contiguous segments; no gap interpolation."""
import csv
import json
import math
from pathlib import Path
import tarfile
import time
import numpy as np
import yaml


def allan_segments(segments, rate, sizes=None, stop=None):
    longest=max(map(len,segments))
    if sizes is None:sizes=np.unique(np.geomspace(1,max(2,longest//10),40).astype(int))
    rows=[]
    prefix=[np.vstack([np.zeros((1,6)),np.cumsum(v,axis=0,dtype=np.float64)]) for v in segments]
    for m in sizes:
        if stop is not None and stop.is_set():raise InterruptedError('IMU 分析已停止，数据保留')
        total=np.zeros(6);count=0
        for p in prefix:
            n=len(p)-1
            if n<2*m+1:continue
            delta=(p[2*m:]-2*p[m:-m]+p[:-2*m])/m
            total+=np.sum(delta**2,axis=0);count+=len(delta)
        if count:rows.append([m/rate,*np.sqrt(total/(2*count)),count])
    return np.asarray(rows)


def fit_region(tau,dev,slope,minimum,maximum):
    best=None
    for start in range(len(tau)-3):
        end=start+4
        while end<len(tau) and tau[end-1]/tau[start]<2:end+=1
        x=tau[start:end];y=dev[start:end]
        if x[0]<minimum or x[-1]>maximum or x[-1]/x[0]<2 or np.any(y<=0):continue
        fitted=np.polyfit(np.log(x),np.log(y),1)
        residual=float(np.sqrt(np.mean((np.log(y)-np.polyval(fitted,np.log(x)))**2)))
        error=abs(float(fitted[0])-slope)
        if error>.15:continue
        score=error+residual
        if best is None or score<best[0]:
            coefficient=float(np.median(y*np.sqrt(x))) if slope<0 else float(np.median(y*np.sqrt(3)/np.sqrt(x)))
            best=(score,{'coefficient':coefficient,'slope':float(fitted[0]),'tau_range_s':[float(x[0]),float(x[-1])],'log_residual':residual})
    return None if best is None else best[1]


def analyze(run,stop=None,notify=lambda *_:None,prepared_data=None):
    started=time.monotonic();run=Path(run)
    capture=json.loads((run/'imu_capture.json').read_text())
    notify('IMU_ANALYZING','正在读取 IMU 数据，按连续片段计算 Allan 曲线…')
    # cols: segment, tick_index, host_after_ns, then accel and gyro SI values.
    data=(np.loadtxt(run/'imu_samples.csv',delimiter=',',skiprows=1,usecols=(0,1,5,12,13,14,15,16,17),ndmin=2)
          if prepared_data is None else prepared_data)
    if stop is not None and stop.is_set():raise InterruptedError('工具已停止，采集数据保留')
    if len(data)<100:raise ValueError('IMU 数据不足')
    if not np.all(np.isfinite(data)):raise ValueError('IMU 数据存在非有限数值')
    # Do not treat a packet's 14 samples as 14 separate host-clock observations.
    packet_end=np.r_[np.diff(data[:,2])!=0,True]
    anchors=data[packet_end,:3]
    host=(anchors[:,2]-anchors[0,2])/1e9
    valid=(host>1)&(host<host[-1]-1)
    if valid.sum()<10 or capture['counter_discontinuities']:
        raise ValueError('有效包时间不足或仍存在未识别的计数跳变，保留数据，请先运行计数器诊断')
    slope,offset=np.polyfit(host[valid],anchors[valid,1],1)
    rate=float(slope)
    if not 50<rate<5000:raise ValueError('实测采样速率不合理：'+str(rate))
    residual=anchors[valid,1]-(rate*host[valid]+offset)
    cuts=np.r_[0,np.flatnonzero(np.diff(data[:,0])!=0)+1,len(data)]
    segments=[data[a:b,3:] for a,b in zip(cuts[:-1],cuts[1:]) if b-a>=100]
    if not segments:raise ValueError('没有足够的连续 IMU 数据片段')
    curves=allan_segments(segments,rate,stop=stop)
    with (run/'imu-allan.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['tau_s','ax','ay','az','gx','gy','gz','differences_used']);writer.writerows(curves)
    longest=max(map(len,segments))/rate
    issues=[]
    warnings=[]
    if capture['status']!='CAPTURE_COMPLETED':warnings.append('录制提前结束；按实际保留的数据分析')
    if capture['elapsed_seconds']<7200:warnings.append('本次少于建议的 2～3 小时，请结合曲线判断长期噪声是否充分观测')
    gyro=np.linalg.norm(data[:,6:],axis=1)
    accel=np.linalg.norm(data[:,3:6],axis=1)
    if np.quantile(gyro,.99)>.15 or np.std(accel)>.15:issues.append('疑似存在运动或振动，需要检查静止条件')
    fits=[]
    for axis in range(6):
        fits.append({'white_noise':fit_region(curves[:,0],curves[:,axis+1],-.5,.02,2),
                     'bias_random_walk':fit_region(curves[:,0],curves[:,axis+1],.5,10,float(curves[-1,0]))})
    if any(x['white_noise'] is None or x['bias_random_walk'] is None for x in fits):issues.append('部分轴未识别到可靠的白噪声或随机游走斜率区间')
    report={'status':'IMU_NOISE_REVIEW_PENDING' if not issues else 'IMU_ANALYSIS_NEEDS_REVIEW',
        'quality_accepted':False,'ready_for_camera_imu':False,
        'samples':len(data),'segments':len(segments),'longest_segment_seconds':longest,
        'estimated_sample_rate_hz':rate,'clock_fit_residual_std_samples':float(np.std(residual)),
        'time_basis':'Empirical host-clock/counter fit, not vendor-confirmed hardware time; not exposure synchronization.',
        'issues':issues,'warnings':warnings,'capture_status':capture['status'],'elapsed_seconds':capture['elapsed_seconds'],'axis_fits':fits,'wall_seconds':time.monotonic()-started}
    if not issues:
        profile={'rostopic':'/imu0','update_rate':rate,
          'accelerometer_noise_density':max(fits[i]['white_noise']['coefficient'] for i in range(3)),
          'accelerometer_random_walk':max(fits[i]['bias_random_walk']['coefficient'] for i in range(3)),
          'gyroscope_noise_density':max(fits[i]['white_noise']['coefficient'] for i in range(3,6)),
          'gyroscope_random_walk':max(fits[i]['bias_random_walk']['coefficient'] for i in range(3,6))}
        (run/'imu-candidate.yaml').write_text('# Experimental noise candidate; review required. Not a hardware timestamp calibration.\n'+yaml.safe_dump(profile,sort_keys=False))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    for group,title,unit in [(0,'Accelerometer','m/s^2'),(1,'Gyroscope','rad/s')]:
        for axis,name in enumerate('XYZ'):
            axes[group].loglog(curves[:,0],curves[:,1+group*3+axis],label=name)
        axes[group].set(xlabel='Averaging time (s)',ylabel='Allan deviation ('+unit+')',title=title)
        axes[group].grid(True,which='both',alpha=.3);axes[group].legend()
    fig.suptitle('IMU noise analysis — review pending')
    fig.tight_layout();fig.savefig(run/'imu-report.pdf');plt.close(fig)
    (run/'imu-analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (run/'imu-results.txt').write_text('Status: '+report['status']+'\nSamples: '+str(len(data))+'\nEstimated sample rate Hz: '+str(rate)+'\nLongest segment s: '+str(longest)+'\nReview: '+('; '.join(issues) or 'Candidate generated; independent review required')+'\n',encoding='utf-8')
    with tarfile.open(run/'imu_small_review.tar.gz','w:gz') as tar:
        for name in ['imu_capture.json','imu-analysis.json','imu-results.txt','imu-report.pdf','imu-allan.csv','imu-candidate.yaml','recovery.json','original_imu_capture.json']:
            if (run/name).is_file():tar.add(run/name,arcname=name)
    return report
