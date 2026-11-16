"""Experimental host/counter mapping and fully read-back-verified joint BAG.

This is an explicit timing assumption for experiments, never exposure sync.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from bag_writer import Backend, pixels, require, sha


def map_times(samples, manifest, clock):
    ticks=samples['tick_index'].astype(np.float64)
    require(len(ticks)>100 and np.all(np.diff(ticks)>0),'Non-increasing or insufficient IMU ticks')
    ends=np.r_[np.diff(samples['packet'])!=0,True]
    host=samples['host_after_ns'][ends].astype(np.int64)
    require(len(host)>10 and np.all(np.diff(host)>0),'Insufficient/non-increasing packet host anchors')
    first_host=int(host[0])
    x=(host-first_host)/1e9
    rate,offset=np.polyfit(x,ticks[ends],1)
    require(50<rate<5000,'Unreasonable empirical sample rate')
    image_times=np.asarray([p['timestamp_ns'] for p in manifest['selected_pairs']],dtype=np.int64)
    require(np.all(np.diff(image_times)>0),'Non-increasing image times')
    image_origin=int(image_times[0])-int(clock['unix_ns'])+int(clock['monotonic_ns'])
    imu_times=np.rint((ticks-offset)/rate*1e9).astype(np.int64)+(first_host-image_origin)+10**9
    images=image_times-int(image_times[0])+10**9
    require(np.all(imu_times>0) and np.all(np.diff(imu_times)>0),'Invalid experimental sample timestamps')
    residual=(ticks[ends]-(rate*x+offset))/rate*1000
    report={'status':'EXPERIMENTAL_TIME_MODEL_NOT_SYNC_VERIFIED',
        'empirical_rate_hz':float(rate),'packet_anchors':len(host),
        'counter_tick_offset':float(offset),'host_anchor_origin_ns':first_host,
        'image_monotonic_origin_ns':image_origin,'bag_image_origin_ns':10**9,
        'formula':'tick = rate * (packet_host_after - first_packet_host_after) + offset; invert fit per observed tick; image host times share the same relative origin.',
        'fit_residual_std_ms':float(np.std(residual)),
        'fit_residual_min_ms':float(residual.min()),'fit_residual_max_ms':float(residual.max()),
        'hardware_sync_verified':False,'quality_accepted':False,
        'sensor_values_interpolated':False,'gap_times_compressed':False,
        'assumptions':['Each packet last tick is fitted to USB request completion time; unknown transport delay and sample phase remain.',
        'Image timestamps are host frame-completion times, not exposure times.',
        'Constant timing differences may be estimated during an experimental Kalibr run, but variable latency is not corrected.',
        'Fit residuals do not measure camera-IMU synchronization accuracy.']}
    return images,imu_times,report


class JointBackend(Backend):
    def imu(self,seq,n,values):
        sec,ns=divmod(int(n),10**9)
        if self.kind=='rosbag':
            from sensor_msgs.msg import Imu
            m=Imu();m.header.seq=seq;m.header.frame_id='imu0';m.header.stamp=self.rp.Time(sec,ns)
            m.orientation_covariance[0]=-1
            m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z=map(float,values[:3])
            m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z=map(float,values[3:])
            return m
        t=self.store.types
        header=t['std_msgs/msg/Header'](seq,t['builtin_interfaces/msg/Time'](sec,ns),'imu0')
        cov=np.zeros(9);cov[0]=-1
        return t['sensor_msgs/msg/Imu'](header,t['geometry_msgs/msg/Quaternion'](0.,0.,0.,0.),cov,
            t['geometry_msgs/msg/Vector3'](*map(float,values[3:])),np.zeros(9),
            t['geometry_msgs/msg/Vector3'](*map(float,values[:3])),np.zeros(9))

    def image(self,seq,n,eye,data,width,height):
        sec,ns=divmod(int(n),10**9)
        if self.kind=='rosbag':
            m=self.Image();m.header.seq=seq;m.header.frame_id='cam'+str(eye);m.header.stamp=self.rp.Time(sec,ns)
            m.width=width;m.height=height;m.step=width;m.encoding='mono8';m.is_bigendian=0;m.data=data
            return m
        t=self.store.types
        header=t['std_msgs/msg/Header'](seq,t['builtin_interfaces/msg/Time'](sec,ns),'cam'+str(eye))
        return t['sensor_msgs/msg/Image'](header,height,width,'mono8',0,width,np.frombuffer(data,dtype=np.uint8))


def prepare(source,output,backend='rosbag'):
    source,output=Path(source).resolve(),Path(output).resolve()
    require(source!=output,'Use a fresh output directory')
    manifest=json.loads((source/'camera_manifest.json').read_text())
    capture=json.loads((source/'imu_capture.json').read_text())
    require(capture['counter_discontinuities']==0 and capture['duplicates']==0,'Unresolved IMU discontinuities/duplicates')
    samples=np.genfromtxt(source/'imu_samples.csv',delimiter=',',names=True,dtype=None,encoding='utf8')
    require(len(samples)==capture['samples'],'IMU count mismatch')
    values=np.column_stack([samples[k] for k in ['ax_m_s2','ay_m_s2','az_m_s2','gx_rad_s','gy_rad_s','gz_rad_s']])
    require(np.isfinite(values).all(),'Invalid SI values')
    image_times,imu_times,model=map_times(samples,manifest,json.loads((source/'joint_clock.json').read_text()))
    model['source_sha256']={name:sha(source/name) for name in ['imu_samples.csv','camera_manifest.json','joint_clock.json']}
    (output/'experimental_time_model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
    path=output/'camera_imu_experimental.bag'
    require(not path.exists(),'Output BAG already exists')
    engine=JointBackend(backend);expected={}
    events=sorted([(int(n),0,i) for i,n in enumerate(image_times)]+[(int(n),1,i) for i,n in enumerate(imu_times)])
    if backend=='rosbag':writer=engine.rb.Bag(str(path),'w')
    else:
        from rosbags.rosbag1 import Writer
        writer=Writer(path);writer.open()
        connections={topic:writer.add_connection(topic,kind,typestore=engine.store) for topic,kind in [('/cam0/image_raw','sensor_msgs/msg/Image'),('/cam1/image_raw','sensor_msgs/msg/Image'),('/imu0','sensor_msgs/msg/Imu')]}
    def write(topic,n,msg):
        if backend=='rosbag':writer.write(topic,msg,engine.rp.Time(n//10**9,n%10**9))
        else:writer.write(connections[topic],n,engine.store.serialize_ros1(msg,connections[topic].msgtype))
    try:
        for n,kind,index in events:
            if kind==0:
                pair=manifest['selected_pairs'][index]
                for eye,side in enumerate(['left','right']):
                    data=pixels(source,pair[side],manifest['width'],manifest['height'])
                    topic='/cam%d/image_raw'%eye
                    write(topic,n,engine.image(index,n,eye,data,manifest['width'],manifest['height']))
                    expected[(topic,n)]=(index,hashlib.sha256(data).hexdigest())
            else:
                write('/imu0',n,engine.imu(index,n,values[index]))
                expected[('/imu0',n)]=(index,tuple(map(float,values[index])))
    finally:writer.close()
    counts={};previous={}
    for topic,n,m,header in engine.read(path):
        require(n==header and n>previous.get(topic,-1),'Invalid BAG/Header timestamps')
        previous[topic]=n
        require((topic,n) in expected,'Unexpected/duplicate BAG message')
        seq,payload=expected.pop((topic,n))
        require(m.header.seq==seq,'Sequence mismatch')
        if topic=='/imu0':
            observed=(m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z,m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z)
            require(observed==payload and m.orientation_covariance[0]==-1,'IMU values changed')
        else:
            require(m.width==manifest['width'] and m.height==manifest['height'] and m.encoding=='mono8','Image geometry changed')
            require(hashlib.sha256(bytes(m.data)).hexdigest()==payload,'Image pixels changed')
        counts[topic]=counts.get(topic,0)+1
    require(not expected,'Missing BAG messages')
    report={'status':'EXPERIMENTAL_JOINT_BAG_READBACK_VERIFIED','counts':counts,
        'bag_sha256':sha(path),'all_image_pixels_verified':True,'all_imu_values_verified':True,
        'all_header_and_bag_times_verified':True,'hardware_sync_verified':False,
        'quality_accepted':False,'joint_optimization_executed':False}
    (output/'bag_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--backend',choices=['rosbag','rosbags'],default='rosbag')
    a=p.parse_args();prepare(a.source,a.output,a.backend)
