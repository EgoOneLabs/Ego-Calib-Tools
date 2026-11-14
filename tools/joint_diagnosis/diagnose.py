"""Read-only diagnostics for two existing rigid-mount 2UQ2 recordings.

This is a kinematic sensitivity check, not a Kalibr observability test.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import numpy as np
import yaml

RECORDS=['camera_imu_20261114T072623Z_dd4dca05','camera_imu_20261114T075600Z_269e962d']
CANDIDATES=['joint_camera_updated_hDPklVhP/camera_imu-camchain-imucam.yaml','joint_repeat_ik9mmEUn/camera_imu-camchain-imucam.yaml']


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024**2),b''):h.update(chunk)
    return h.hexdigest()


def skew(v):
    x,y,z=map(float,v)
    return np.array([[0,-z,y],[z,0,-x],[-y,x,0.]])


def transforms(path):
    data=yaml.safe_load(path.read_text());T=np.asarray(data['cam0']['T_cam_imu'],dtype=float)
    if T.shape!=(4,4) or not np.isfinite(T).all():raise ValueError('外参格式无效：'+str(path))
    R=T[:3,:3]
    if not np.allclose(R.T@R,np.eye(3),atol=1e-6) or not np.isclose(np.linalg.det(R),1,atol=1e-6):raise ValueError('外参旋转矩阵无效')
    return T,-R.T@T[:3,3]


def motion_metrics(data,rate,delta_r,window_seconds):
    ticks=data['tick_index'];segments=data['segment']
    values=np.column_stack([data[n] for n in ('gx_rad_s','gy_rad_s','gz_rad_s')])
    cuts=np.r_[0,np.flatnonzero((np.diff(segments)!=0)|(np.diff(ticks)!=1))+1,len(data)]
    m=max(2,int(round(rate*window_seconds)));operators=[];angular=[]
    for a,b in zip(cuts[:-1],cuts[1:]):
        n=(b-a)//m
        if n<3:continue
        w=values[a:a+n*m].reshape(n,m,3).mean(axis=1)
        t=ticks[a:a+n*m].reshape(n,m).mean(axis=1)/rate
        alpha=(w[2:]-w[:-2])/(t[2:]-t[:-2])[:,None]
        for omega,domega in zip(w[1:-1],alpha):
            W=skew(omega);operators.append(skew(domega)+W@W)
        angular.extend(w[1:-1])
    if not operators:return dict(window_seconds=window_seconds,status='INSUFFICIENT_CONTIGUOUS_DATA')
    M=np.asarray(operators);w=np.asarray(angular)
    gram=np.einsum('nki,nkj->ij',M,M)/len(M)
    eigen,vectors=np.linalg.eigh(gram);eigen=np.maximum(eigen,0)
    response=np.einsum('nij,j->ni',M,delta_r);norm=np.linalg.norm(response,axis=1)
    return dict(window_seconds=window_seconds,block_samples=m,usable_centers=len(M),
        rms_sensitivity_per_m_s2=np.sqrt(eigen).tolist(),
        weakest_direction_in_imu_axes=vectors[:,0].tolist(),
        sensitivity_ratio_min_over_max=float(np.sqrt(eigen[0]/eigen[-1])) if eigen[-1]>0 else None,
        delta_r_only_acceleration_change_m_s2=dict(mean=float(norm.mean()),rms=float(np.sqrt(np.mean(norm**2))),p95=float(np.quantile(norm,.95))),
        angular_speed_rad_s=dict(mean=float(np.linalg.norm(w,axis=1).mean()),p95=float(np.quantile(np.linalg.norm(w,axis=1),.95))),
        interpretation='Block-averaged measured gyro and central differences within contiguous segments only. Does not include camera reprojection, trajectory, gravity/bias compensation, rotation differences, or time-offset refit. Not a Fisher-information/covariance result or pass/fail threshold.')


def review_record(source,delta_r):
    paths=[source/n for n in ('imu_samples.csv','imu_capture.json','camera_manifest.json','joint_clock.json')]
    for p in paths:
        if not p.is_file():raise ValueError('找不到已有文件：'+str(p))
    data=np.genfromtxt(paths[0],delimiter=',',names=True,dtype=None,encoding='utf8')
    if len(data)<100:raise ValueError('样本不足')
    needed=['segment','tick_index','host_after_ns','gx_rad_s','gy_rad_s','gz_rad_s']
    if not all(k in data.dtype.names for k in needed):raise ValueError('IMU 列格式不匹配')
    ticks=data['tick_index'].astype(np.int64);host=data['host_after_ns'].astype(np.int64)
    if np.any(np.diff(ticks)<=0):raise ValueError('IMU tick_index 回跳，暂不作运动导数分析')
    ends=np.r_[np.diff(host)!=0,True];anchors_host=host[ends];anchors_tick=ticks[ends]
    x=(anchors_host-anchors_host[0])/1e9;valid=(x>1)&(x<x[-1]-1)
    if valid.sum()<10:raise ValueError('有效包时间不足')
    rate,offset=np.polyfit(x[valid],anchors_tick[valid],1)
    if not 50<rate<5000:raise ValueError('经验采样率不合理')
    residual=(anchors_tick[valid]-rate*x[valid]-offset)/rate*1000
    windows=[]
    for start in np.arange(0,max(0,x[-1]-9.9),20):
        mask=(x>=start)&(x<start+20)
        if mask.sum()<100 or np.ptp(x[mask])<9.9:continue
        slope,_=np.polyfit(x[mask]-x[mask][0],anchors_tick[mask]-anchors_tick[mask][0],1)
        windows.append(dict(host_start_s=float(start),observed_span_s=float(np.ptp(x[mask])),rate_hz=float(slope),relative_to_full_fit_ppm=float((slope/rate-1)*1e6)))
    manifest=json.loads(paths[2].read_text());stamps=np.asarray([p['timestamp_ns'] for p in manifest['selected_pairs']],dtype=np.int64)
    if len(stamps)<2 or np.any(np.diff(stamps)<=0):raise ValueError('相机图像时间无效')
    intervals=np.diff(stamps)/1e6
    capture=json.loads(paths[1].read_text())
    if capture.get('counter_discontinuities',0):raise ValueError('存在未识别的计数跳变，不能据此估计运动导数')
    return dict(record=source.name,input_sha256={p.name:sha(p) for p in paths},
        samples=len(data),capture=capture,empirical_rate_hz=float(rate),
        packet_clock_fit_residual_ms=dict(std=float(residual.std()),p95_abs=float(np.quantile(np.abs(residual),.95)),max_abs=float(np.max(np.abs(residual)))),
        clock_windows=windows,
        camera_interval_ms=dict(median=float(np.median(intervals)),p95=float(np.quantile(intervals,.95)),max=float(intervals.max())),
        kinematic_sensitivity=[motion_metrics(data,rate,delta_r,s) for s in (.04,.1,.2)],
        caveat='Host packet completion and complete-frame timestamps are not exposure/sample hardware timestamps. These diagnostics cannot verify synchronization or manufacturer scaling.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/home/key/文档/kalibr/data/camera_imu/2UQ2'))
    args=parser.parse_args();base=args.root.resolve()
    if not base.is_dir():raise ValueError('请在保存两段原始录制的原 Linux 工作站 key@key 上执行；找不到 '+str(base))
    files=[base/p for p in CANDIDATES]
    A,rA=transforms(files[0]);B,rB=transforms(files[1]);delta=rB-rA
    out=Path(tempfile.mkdtemp(prefix='joint_diagnosis_',dir=base))
    report=dict(status='DIAGNOSTIC_ONLY_NOT_ACCEPTANCE',created_utc=datetime.now(timezone.utc).isoformat(),source_files_modified=False,
        translation_centers_difference_mm=float(np.linalg.norm(delta)*1000),delta_camera_center_in_imu_axes_mm=(delta*1000).tolist(),
        candidate_sha256={str(p):sha(p) for p in files},records=[],
        limitations=['Empirical clock fit is not hardware synchronization verification.','Recorded SI scale and axes remain manufacturer-confirmation items.',
        'Motion sensitivity is not full Kalibr observability or parameter confidence.','No source BAG/CSV/YAML is changed. No interpolation across sample gaps.'])
    try:
        for name in RECORDS:
            print('读取已有数据：'+name,flush=True);report['records'].append(review_record(base/name,delta))
        lines=['已有两段数据诊断（不作自动验收）',f'相机中心位置差：{report["translation_centers_difference_mm"]:.3f} mm','']
        for rec in report['records']:
            lines.extend([rec['record'],f'经验采样率 {rec["empirical_rate_hz"]:.6f} Hz；包主机时间拟合残差标准差 {rec["packet_clock_fit_residual_ms"]["std"]:.3f} ms'])
            for m in rec['kinematic_sensitivity']:
                if m.get('status'):lines.append(str(m));continue
                a=m['delta_r_only_acceleration_change_m_s2']
                lines.append(f"分块 {m['window_seconds']*1000:.0f} ms：仅杠杆臂差异预计加速度变化 RMS {a['rms']:.6f} m/s²；方向灵敏度比 {str(round(m['sensitivity_ratio_min_over_max'],4)) if m['sensitivity_ratio_min_over_max'] is not None else '未定义（零运动）'}")
            lines.append('')
        lines.extend(['以上为诊断，不能据此宣布外参准确、硬件同步或噪声验收。','不需要重录；请回传本目录的小检查包继续判断。'])
        (out/'diagnosis.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True)
    except Exception as exc:
        report['status']='DIAGNOSTIC_FAILED';report['error']=str(exc);raise
    finally:
        (out/'diagnosis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        with tarfile.open(out/'joint_diagnosis_review.tar.gz','w:gz') as tar:
            for p in out.iterdir():
                if p.suffix in ('.json','.txt'):tar.add(p,arcname=p.name)
        print('\n结果目录：'+str(out)+'\n请回传：'+str(out/'joint_diagnosis_review.tar.gz'),flush=True)
        subprocess.run(['xdg-open',str(out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:raise SystemExit('已停止诊断，原始数据不变。')
    except Exception as exc:raise SystemExit('诊断停止：'+str(exc))
