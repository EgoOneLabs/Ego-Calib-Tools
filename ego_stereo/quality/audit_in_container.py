#!/usr/bin/env python3
"""ROS1 BAG offline validation with installed Kalibr camera/detector bindings."""
import argparse,csv,json,hashlib,time,resource
from pathlib import Path
import numpy as np
from audit_core import cross_residuals,stats,coverage


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    import cv2,rosbag,aslam_cv as acv,aslam_cameras_april as april,kalibr_common as kc
    from cv_bridge import CvBridge
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--bag',required=True);a=a.parse_args()
    root=a.root;started=time.monotonic();usage=resource.getrusage(resource.RUSAGE_SELF)
    chain=kc.ConfigReader.CameraChainParameters(str(root/'camchain.yaml'))
    if chain.numCameras()!=2:raise ValueError('Expected exactly two cameras')
    cameras=[kc.ConfigReader.AslamCamera.fromParameters(chain.getCameraParameters(i)) for i in range(2)]
    geometries=[c.geometry for c in cameras]
    detectors=[]
    for camera in cameras:
        target=april.GridCalibrationTargetAprilgrid(6,6,0.088,0.3)
        options=acv.GridDetectorOptions();options.filterCornerOutliers=True
        detectors.append(acv.GridDetector(camera.geometry,target,options))
    t10=chain.getExtrinsicsLastCamToHere(1)
    transforms=[t10.inverse(),t10]
    topics=[chain.getCameraParameters(i).getRosTopic() for i in range(2)]
    if topics!=['/cam0/image_raw','/cam1/image_raw']:raise ValueError('Unexpected topic order')
    bridge=CvBridge();pending={};seen=set();counts=[0,0];successes=[0,0];pairs=0;common_pairs=0
    vectors={k:[] for k in ['mono_cam0','mono_cam1','cross_to_cam0','cross_to_cam1']}
    grids=[np.zeros((6,8),int),np.zeros((6,8),int)];outside=[0,0]
    worst=None;worst_rms=-1;first_saved=False

    def evidence(name,images,cross,pair_index):
        panels=[]
        for camera,image in enumerate(images):
            color=cv2.cvtColor(image,cv2.COLOR_GRAY2BGR)
            for _,observed,projected,_ in cross[camera]:
                o=tuple(np.rint(observed).astype(int));p=tuple(np.rint(projected).astype(int))
                # Green = detected; red = prediction from the other camera.
                if all(abs(v)<100000 for v in o+p):
                    cv2.circle(color,o,4,(0,220,0),1);cv2.circle(color,p,4,(0,0,255),1);cv2.line(color,o,p,(0,200,255),1)
            color=cv2.resize(color,(960,540))
            cv2.putText(color,'cam%d: green=observed red=cross-predicted'%camera,(12,26),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
            panels.append(color)
        canvas=np.hstack(panels)
        cv2.putText(canvas,'Pair %d; display scaled 0.5x; reported errors are ORIGINAL pixels'%pair_index,(12,525),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,255,255),1)
        if not cv2.imwrite(str(root/name),canvas):raise RuntimeError('Failed to write evidence image')

    with (root/'corner_residuals.csv').open('w',newline='') as f,rosbag.Bag(a.bag,'r') as bag:
        writer=csv.writer(f);writer.writerow(['pair_index','timestamp_ns','kind','destination_camera','corner_id','observed_u','observed_v','predicted_u','predicted_v','dx_px','dy_px'])
        for topic,msg,stamp in bag.read_messages(topics=topics):
            camera=topics.index(topic);ns=msg.header.stamp.to_nsec();key=(camera,ns)
            if key in seen:raise ValueError('Duplicate image timestamp in one camera')
            seen.add(key);counts[camera]+=1
            if stamp.to_nsec()!=ns:raise ValueError('BAG time and Header time differ')
            pair=pending.setdefault(ns,{})
            if msg._type!='sensor_msgs/Image':raise ValueError('Expected raw ROS Image')
            image=bridge.imgmsg_to_cv2(msg,desired_encoding='mono8')
            if image.shape!=(1080,1920):raise ValueError('Unexpected image dimensions')
            pair[camera]=(msg.header.stamp,image.copy())
            if len(pending)>8:raise ValueError('Too many unmatched frames; refuse approximate pairing')
            if len(pair)!=2:continue
            del pending[ns];images=[pair[i][1] for i in range(2)];observations=[];valid=[]
            for i in range(2):
                ts=pair[i][0];ok,obs=detectors[i].findTarget(acv.Time(ts.secs,ts.nsecs),images[i]);valid.append(bool(ok));observations.append(obs)
                if not ok:continue
                successes[i]+=1
                observed=np.asarray(obs.getCornersImageFrame()).reshape(-1,2)
                predicted=np.asarray(obs.getCornerReprojection(geometries[i])).reshape(-1,2)
                ids=np.asarray(obs.getCornersIdx()).reshape(-1)
                if len(observed)!=len(predicted) or len(ids)!=len(observed):raise ValueError('Mono array size mismatch')
                grid,out=coverage(observed,1920,1080);grids[i]+=grid;outside[i]+=out
                for corner_id,uv,pr in zip(ids,observed,predicted):
                    error=pr-uv
                    if not np.isfinite(error).all():raise ValueError('Non-finite mono residual')
                    vectors['mono_cam%d'%i].append(error)
                    writer.writerow([pairs,ns,'mono',i,int(corner_id),*uv,*pr,*error])
            cross=[[],[]]
            if all(valid):
                for dest in range(2):
                    source=1-dest
                    cross[dest]=cross_residuals(observations[source],observations[dest],geometries[dest],transforms[dest])
                    for corner_id,uv,pr,error in cross[dest]:
                        vectors['cross_to_cam%d'%dest].append(error)
                        writer.writerow([pairs,ns,'cross',dest,corner_id,*uv,*pr,*error])
                if cross[0]:
                    common_pairs+=1
                    values=[row[3] for rows in cross for row in rows];rms=stats(values)['rms_l2_px']
                    if rms>worst_rms:worst_rms=rms;worst=([im.copy() for im in images],cross,pairs)
                    if not first_saved:evidence('first_cross_projection.jpg',images,cross,pairs);first_saved=True
                    if pairs in [115,229]:evidence('cross_projection_%03d.jpg'%pairs,images,cross,pairs)
            pairs+=1
            if pairs%20==0:print('已核查 %d 对；双眼共同有效 %d 对'%(pairs,common_pairs),flush=True)
    if pending:raise ValueError('Unpaired images remain')
    if counts!=[230,230] or pairs!=230:raise ValueError('Expected original 230 pairs, got %r'%counts)
    if worst:evidence('worst_cross_projection.jpg',*worst)
    grid_report=[]
    heat=np.zeros((2*300,800,3),np.uint8)
    for i,grid in enumerate(grids):
        occupied=int((grid>0).sum())
        grid_report.append({'grid_rows':6,'grid_cols':8,'counts':grid.tolist(),'cells_with_any_corner':occupied,'total_cells':48,'fraction_cells_with_any_corner':occupied/48,'outside_image_count':outside[i],'meaning':'Observed cells only; not area coverage, not a quality threshold'})
        for row in range(6):
            for col in range(8):
                v=int(grid[row,col]);intensity=int(230*np.log1p(v)/max(1,np.log1p(grid.max())))
                y=i*300+row*50;x=col*100
                cv2.rectangle(heat,(x,y),(x+99,y+49),(20,intensity,30),-1)
                cv2.putText(heat,str(v),(x+8,y+32),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
    if not cv2.imwrite(str(root/'coverage_counts_cam0_top_cam1_bottom.png'),heat):raise RuntimeError('Failed to write coverage')
    elapsed=time.monotonic()-started;after=resource.getrusage(resource.RUSAGE_SELF)
    result={'status':'FIXED_PARAMETER_OBSERVATIONS_COMPLETE_REVIEW_PENDING' if common_pairs else 'NO_COMMON_TARGET_OBSERVATIONS',
            'input_pairs':pairs,'detected_pairs_per_camera':successes,'common_target_pairs':common_pairs,
            'residuals':{key:stats(value) for key,value in vectors.items()},'coverage':grid_report,
            'timing_seconds':{'real':elapsed,'user':after.ru_utime-usage.ru_utime,'sys':after.ru_stime-usage.ru_stime},
            'intrinsics_optimized':False,'stereo_extrinsics_optimized':False,'independent_holdout':False,
            'corner_outlier_filter':'Kalibr GridDetectorOptions.filterCornerOutliers=True; applies before these statistics',
            'calibration_quality_accepted':False,'hardware_sync_verified':False,
            'physical_board_dimensions_verified':False,'device_unit_association_verified':False,
            'reference_method':'Official kalibr_camera_validator mono/cross-camera reprojection with fixed camera parameters; offline adapter, not official validator executable'}
    dump(root/'quality_summary.json',result)
    print(result['status'],flush=True)
    if not common_pairs:raise ValueError('No common detections; no quality conclusion possible')

if __name__=='__main__':main()
