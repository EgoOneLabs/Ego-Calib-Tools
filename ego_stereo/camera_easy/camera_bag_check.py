"""Read an existing ROS1 stereo BAG without claiming source-pixel verification."""
import hashlib
import json
import math
from pathlib import Path
import sys


def check(root,bag_factory=None,joint=False):
    if bag_factory is None:
        import rosbag
        bag_factory=rosbag.Bag
    root=Path(root);bag=root/('camera_imu_experimental.bag' if joint else 'camera.bag');topics=['/cam0/image_raw','/cam1/image_raw']
    if joint:topics.append('/imu0')
    counts=dict.fromkeys(topics,0);last={};first={};geometry={}
    with bag_factory(str(bag),'r') as stream:
        for topic,msg,_ in stream.read_messages(topics=topics):
            if topic=='/imu0':
                if getattr(msg,'_type','')!='sensor_msgs/Imu':raise ValueError('需要 sensor_msgs/Imu：/imu0')
                values=[getattr(v,k) for v in (msg.linear_acceleration,msg.angular_velocity) for k in ('x','y','z')]
                if not all(math.isfinite(x) for x in values):raise ValueError('IMU 存在非有限数值')
                stamp=msg.header.stamp.to_nsec()
                if stamp<=0 or stamp<=last.get(topic,0):raise ValueError('IMU 时间戳无效或回跳')
                first.setdefault(topic,stamp);last[topic]=stamp;counts[topic]+=1
                continue
            if getattr(msg,'_type','')!='sensor_msgs/Image':raise ValueError('需要未压缩 sensor_msgs/Image：'+topic)
            if msg.width<=0 or msg.height<=0 or msg.step<=0 or len(msg.data)!=msg.height*msg.step:
                raise ValueError('图像尺寸或数据长度无效：'+topic)
            if msg.encoding not in ('mono8','rgb8','bgr8'):raise ValueError('不支持的图像编码：'+msg.encoding)
            channels=1 if msg.encoding=='mono8' else 3
            if msg.step<msg.width*channels:raise ValueError('图像行宽无效：'+topic)
            dims=(msg.width,msg.height)
            if topic in geometry and geometry[topic]!=dims:raise ValueError('录制中图像尺寸变化：'+topic)
            geometry[topic]=dims
            stamp=msg.header.stamp.to_nsec()
            if stamp<=0 or stamp<=last.get(topic,0):raise ValueError('图像时间戳无效或回跳：'+topic)
            first.setdefault(topic,stamp);last[topic]=stamp;counts[topic]+=1
            if sum(counts.values())%100==0:print('已读取图像：'+str(counts),flush=True)
    if min(counts[t] for t in topics[:2])<40:raise ValueError('每个相机至少需要 40 帧输入；这不是质量通过条件')
    if joint:
        if counts['/imu0']<100:raise ValueError('联合 BAG 缺少足够 /imu0 样本')
        if max(first.values())>=min(last.values()):raise ValueError('图像与 IMU 没有重叠时间区间')
    digest=hashlib.sha256()
    with bag.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024**2),b''):digest.update(chunk)
    report=dict(status='JOINT_IMPORTED_BAG_CHECKED' if joint else 'CAMERA_EXISTING_BAG_CHECKED',counts=counts,geometry=geometry,bag_sha256=digest.hexdigest(),
                original_pixels_verified_against_manifest=False,calibration_quality_accepted=False,
                timestamp_source='Imported BAG header timestamps used as supplied; exposure/synchronization not verified',
                imu_units_assumption='sensor_msgs/Imu SI: m/s^2 and rad/s' if joint else None)
    (root/'bag_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return report


if __name__=='__main__':check(sys.argv[1],joint='--joint' in sys.argv[2:])
