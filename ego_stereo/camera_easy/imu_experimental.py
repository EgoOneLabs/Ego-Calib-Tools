"""Exploratory mixed Allan model from the 2026-11-03 workflow; not acceptance."""
import json
from pathlib import Path
import hashlib
import tarfile
import numpy as np
import yaml
from scipy.optimize import least_squares

def fit(tau,adev):
    # Positive terms: adev² = N²/tau + P² + K²*tau/3.
    # P absorbs a plateau phenomenologically; it is not exported as a Kalibr parameter.
    first=np.array([np.median(adev*np.sqrt(tau)),np.min(adev)/2,np.median(adev*np.sqrt(3/tau))])
    def residual(logp):
        n,p,k=np.exp(logp)
        return .5*np.log(n*n/tau+p*p+k*k*tau/3)-np.log(adev)
    r=least_squares(residual,np.log(first),bounds=(-35,5),max_nfev=2000)
    n,p,k=np.exp(r.x)
    return {'N':float(n),'plateau':float(p),'K':float(k),'log_rmse':float(np.sqrt(np.mean(residual(r.x)**2))),'success':bool(r.success)}


def generate(run):
    run=Path(run)
    csv=run/'imu-allan.csv'
    analysis=json.loads((run/'imu-analysis.json').read_text())
    a=np.genfromtxt(csv,delimiter=',',names=True)
    a=np.atleast_1d(a)
    keep=(a['tau_s']>=.2)&(a['tau_s']<=65)&(a['differences_used']>=100)
    tau=a['tau_s'][keep]
    if len(tau)<8 or tau[-1]/tau[0]<10:
        raise ValueError('当前曲线的可用时间范围不足以进行实验混合拟合；保留现有报告，不生成权重。')
    results={}
    for axis in ['ax','ay','az','gx','gy','gz']:
        dev=a[axis][keep]
        if not np.isfinite(dev).all() or np.any(dev<=0):
            raise ValueError('Allan 曲线含无效数值：'+axis)
        results[axis]=fit(tau,dev)
        if not results[axis]['success']:
            raise ValueError('实验混合模型未收敛：'+axis)
    weights={'rostopic':'/imu0','update_rate':analysis['estimated_sample_rate_hz']}
    for sensor,axes in [('accelerometer',['ax','ay','az']),('gyroscope',['gx','gy','gz'])]:
        for field,col in [('noise_density','N'),('random_walk','K')]:
            weights[sensor+'_'+field]=max(results[axis][col] for axis in axes)
    if not all(np.isfinite(v) and v>0 for k,v in weights.items() if k!='rostopic'):
        raise ValueError('实验拟合得到无效权重')
    report={'status':'EXPERIMENTAL_WEIGHTS_REVIEW_PENDING','quality_accepted':False,
        'ready_for_camera_imu':False,'method':'Allan variance = N^2/tau + P^2 + K^2*tau/3; log-space least squares',
        'aggregation':'Maximum across three axes of the supplied whole-record curve only; no quarter curves supplied; not a confidence bound.',
        'source_allan_sha256':hashlib.sha256(csv.read_bytes()).hexdigest(),
        'source_analysis_sha256':hashlib.sha256((run/'imu-analysis.json').read_bytes()).hexdigest(),
        'tau_range_s':[float(tau[0]),float(tau[-1])],'points':len(tau),
        'results':results,'weights':weights,
        'limitations':['Mixed-model K is not proof of an independently observed +0.5 slope.',
        'Static drift or vibration can affect fitted weights; no hardware fault conclusion.',
        'Nominal SI and empirical time basis are unchanged; no intrinsic or exposure-time calibration.',
        'Experimental optimizer weights only; validate dynamic residuals and cross-recording repeatability.']}
    if (run/'imu-experimental.yaml').exists() or (run/'imu-experimental-fit.json').exists():
        raise ValueError('实验结果已经存在，未覆盖。')
    (run/'imu-experimental-fit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (run/'imu-experimental.yaml').write_text('# EXPERIMENTAL optimizer weights, not accepted sensor parameters.\n# Mixed white + plateau + walk model; no claim of independently identified random walk.\n# Whole-record curve only; review companion JSON, dynamic residuals and repeatability.\n'+yaml.safe_dump(weights,sort_keys=False))
    with tarfile.open(run/'imu_experimental_review.tar.gz','w:gz') as tar:
        for name in ['imu-experimental.yaml','imu-experimental-fit.json','imu-analysis.json','imu-allan.csv','imu_capture.json','imu-report.pdf','imu-results.txt']:
            if (run/name).is_file():tar.add(run/name,arcname=name)
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('run',type=Path)
    print(json.dumps(generate(p.parse_args().run),ensure_ascii=False,indent=2))
