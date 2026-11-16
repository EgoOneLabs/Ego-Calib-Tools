"""Fit an exploratory Allan white + plateau + random-walk model; not a sensor certification."""
from pathlib import Path
import json
import numpy as np
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

def main():
    out=Path(__file__).parent;results={}
    for name in ['all','quarter1','quarter2','quarter3','quarter4']:
        a=np.genfromtxt(out/(name+'_allan.csv'),delimiter=',',names=True)
        keep=(a['tau_s']>=.2)&(a['tau_s']<=65)&(a['overlapping_windows']>=100)
        results[name]={axis:fit(a['tau_s'][keep],a[axis][keep]) for axis in ['ax','ay','az','gx','gy','gz']}
    # Shared Kalibr weights cover the largest fitted coefficient among axes and time quarters.
    # This is a reproducible aggregation policy, not proof of stationarity or a confidence bound.
    weights={}
    for sensor,axes in [('accelerometer',['ax','ay','az']),('gyroscope',['gx','gy','gz'])]:
        for field,col in [('noise_density','N'),('random_walk','K')]:
            weights[sensor+'_'+field]=max(v[axis][col] for v in results.values() for axis in axes)
    raw=json.loads((out/'raw_review.json').read_text());weights['update_rate']=raw['empirical_rate_hz']
    text='# EXPERIMENTAL: nominal SI, empirical timing, nonstationary static recording.\n# Fitted white + plateau + walk model; shared coefficients are maxima across axes/quarters.\n# No bias or scale correction applied. Validate camera-IMU residuals before acceptance.\n# Topic below is the intended bag adapter topic; verify it matches the generated bag.\nrostopic: /imu0\n'
    text+='\n'.join(k+': '+format(v,'.10g') for k,v in weights.items())+'\n'
    (out/'imu_experimental.yaml').write_text(text)
    (out/'model_fit.json').write_text(json.dumps({'method':'log-space least squares; tau 0.2–65s; Allan²=N²/tau+P²+K²*tau/3','results':results,'weights':weights,'accepted_sensor_parameters':False,'purpose':'Initial camera-IMU optimization weights, subject to dynamic residual validation','aggregation':'Maximum fitted coefficient across all axes and all/four time quarters; no claim of uncertainty bound'},indent=2)+'\n')
    print(text)
if __name__=='__main__':main()
