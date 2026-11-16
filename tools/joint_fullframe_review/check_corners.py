"""Check all original stereo frames with installed Kalibr detector bindings."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
import yaml
from bag_writer import pixels


def main(source, output):
    import aslam_cv as acv
    import aslam_cameras_april as april
    import kalibr_common as kc
    started=time.monotonic()
    manifest=json.loads((source/'camera_manifest.json').read_text())
    board=yaml.safe_load((source/'aprilgrid.yaml').read_text())
    chain=kc.ConfigReader.CameraChainParameters(str(output/'camera.yaml'))
    cameras=[kc.ConfigReader.AslamCamera.fromParameters(chain.getCameraParameters(i)) for i in range(2)]
    detectors=[]
    for camera in cameras:
        target=april.GridCalibrationTargetAprilgrid(int(board['tagRows']),int(board['tagCols']),float(board['tagSize']),float(board['tagSpacing']))
        options=acv.GridDetectorOptions();options.filterCornerOutliers=True
        detectors.append(acv.GridDetector(camera.geometry,target,options))
    counts=[0,0];corners=[0,0];common=0;rows=[]
    grids=[np.zeros((6,8),dtype=int),np.zeros((6,8),dtype=int)]
    for index,pair in enumerate(manifest['selected_pairs']):
        ns=pair['timestamp_ns'];sec,nsec=divmod(ns,10**9)
        valid=[];row={'index':index,'timestamp_ns':ns}
        for eye,side in enumerate(['left','right']):
            data=pixels(source,pair[side],1920,1080)
            image=np.frombuffer(data,dtype=np.uint8).reshape(1080,1920)
            ok,obs=detectors[eye].findTarget(acv.Time(sec,nsec),image)
            valid.append(bool(ok))
            uv=np.asarray(obs.getCornersImageFrame()).reshape(-1,2) if ok else np.empty((0,2))
            counts[eye]+=int(bool(ok));corners[eye]+=len(uv)
            row['cam'+str(eye)]={'pose_detected':bool(ok),'corners':len(uv)}
            for x,y in uv:
                if 0<=x<1920 and 0<=y<1080:grids[eye][min(5,int(y*6/1080)),min(7,int(x*8/1920))]+=1
        common+=int(all(valid));rows.append(row)
        if (index+1)%20==0:print(f'已检查 {index+1}/{len(manifest["selected_pairs"])} 对；双眼均检出 {common} 对',flush=True)
    report={'status':'ALL_FRAME_DETECTION_REVIEW_PENDING','input_pairs':len(rows),
        'detected_pairs_per_camera':counts,'common_pose_pairs':common,'corner_counts':corners,
        'coverage_corner_counts':[g.tolist() for g in grids], 'per_frame':rows,
        'wall_seconds':time.monotonic()-started,'quality_accepted':False,
        'hardware_sync_verified':False,'joint_optimization_executed':False,
        'note':'Official Kalibr detector bindings; original pixels verified against manifest. Detection and coverage are observations, not an accuracy acceptance threshold.'}
    (output/'corner_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('全帧检查完成。',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();main(a.source,a.output)
