import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from data_import import DataImport,relative_name,CHUNK
from offline import inventory

BOARD=dict(rows=6,cols=6,tag_mm=88,gap_mm=26.4)


class ImportTests(unittest.TestCase):
    def manager(self,root):
        app=SimpleNamespace(lock=threading.RLock(),data_root=root,container='fixture',state={'stage':'READY'},offline=SimpleNamespace(busy=lambda:False))
        return DataImport(app)

    def transfer(self,m,mode,files):
        created=m.create(dict(mode=mode,board=BOARD,files=[dict(name=n,size=len(v)) for n,v in files.items()]))
        for i,(name,data) in enumerate(files.items()):m.chunk(created['id'],i,0,io.BytesIO(data),len(data))
        return created

    def test_camera_bag_renamed_and_catalogued_only_after_complete(self):
        with tempfile.TemporaryDirectory() as d:
            m=self.manager(Path(d));data=b'#ROSBAG V2.0\nfixture'
            created=m.create(dict(mode='camera',board=BOARD,files=[dict(name='my camera.bag',size=len(data))]))
            self.assertEqual(inventory(Path(d))[0],{})
            m.chunk(created['id'],0,0,io.BytesIO(data),len(data))
            result=m.finish(created['id']);root=Path(result['path'])
            self.assertEqual((root/'camera.bag').read_bytes(),data)
            self.assertFalse((root/'aprilgrid.yaml').exists());self.assertIsNone(m.active)
            self.assertEqual(inventory(Path(d))[0][result['id']],(root,'camera'))

    def test_joint_bag_and_board_can_be_selected_together(self):
        with tempfile.TemporaryDirectory() as d:
            m=self.manager(Path(d));created=self.transfer(m,'camera_imu',{'record.bag':b'#ROSBAG V2.0\nfixture','aprilgrid.yaml':b'target_type: aprilgrid\ntagRows: 6\ntagCols: 6\ntagSize: 0.04\ntagSpacing: 0.3\n'})
            result=m.finish(created['id']);self.assertEqual(result['kind'],'imported_joint')
            self.assertIn('tagSize: 0.04',(Path(result['path'])/'aprilgrid.yaml').read_text())

    def test_imu_folder_selection_checks_required_files(self):
        with tempfile.TemporaryDirectory() as d:
            m=self.manager(Path(d))
            csv=b'segment,tick_index,counter_raw,packet,host_before_ns,host_after_ns,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,ax_m_s2,ay_m_s2,az_m_s2,gx_rad_s,gy_rad_s,gz_rad_s\n'
            capture=json.dumps(dict(status='CAPTURE_COMPLETED',elapsed_seconds=7200,counter_discontinuities=0)).encode()
            created=self.transfer(m,'imu',{'my-record/imu_samples.csv':csv,'my-record/imu_capture.json':capture})
            result=m.finish(created['id']);self.assertEqual(result['kind'],'imu')
            self.assertTrue((Path(result['path'])/'imu_samples.csv').exists())

    def test_partial_transfer_and_missing_metadata_are_rejected_and_cancelled(self):
        with tempfile.TemporaryDirectory() as d:
            m=self.manager(Path(d));created=m.create(dict(mode='imu',files=[dict(name='imu_samples.csv',size=2)]))
            with self.assertRaisesRegex(ValueError,'尚未传完'):m.finish(created['id'])
            m.chunk(created['id'],0,0,io.BytesIO(b'ab'),2)
            with self.assertRaisesRegex(ValueError,'imu_capture.json'):m.finish(created['id'])
            root=m.active['root'];m.abort(created['id']);self.assertFalse(root.exists());self.assertIsNone(m.active)

    def test_path_escape_offsets_and_forged_marker_are_rejected(self):
        for name in ('../a.bag','/a.bag','a/../x.bag','.import-ready.json','a\\x.bag'):
            with self.subTest(name=name),self.assertRaises(ValueError):relative_name(name)
        with tempfile.TemporaryDirectory() as d:
            m=self.manager(Path(d));created=m.create(dict(mode='camera',files=[dict(name='camera.bag',size=10)]))
            with self.assertRaisesRegex(ValueError,'位置'):m.chunk(created['id'],0,5,io.BytesIO(b'12'),2)
            with self.assertRaises(ValueError):m.chunk(created['id'],0,0,io.BytesIO(),CHUNK+1)
            self.assertEqual(m.active['files'][0]['offset'],0)

    def test_space_and_active_capture_prevent_import(self):
        with tempfile.TemporaryDirectory() as d:
            m=self.manager(Path(d));value=dict(mode='camera',files=[dict(name='camera.bag',size=20)])
            with patch('data_import.shutil.disk_usage',return_value=SimpleNamespace(free=100)):
                with self.assertRaisesRegex(ValueError,'空间不足'):m.create(value)
            m.app.state['stage']='IMU_RECORDING'
            with self.assertRaisesRegex(ValueError,'录制或计算'):m.create(value)


if __name__=='__main__':unittest.main()

class ImportHttpTests(unittest.TestCase):
    def test_chunk_endpoint_streams_binary_and_checks_token_before_writing(self):
        import urllib.request
        import urllib.error
        from app import Handler,ThreadingHTTPServer
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);m=ImportTests().manager(root);app=m.app;app.imports=m
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.token='valid';server.app=app
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def post(path,data,token='valid'):
                raw=data if isinstance(data,bytes) else json.dumps(data).encode()
                req=urllib.request.Request(base+path,data=raw,headers={'X-Ego-Token':token},method='POST')
                with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
            try:
                bag=b'#ROSBAG V2.0\n'+b'\x00\xff'*100
                created=post('/imports/create',dict(mode='camera',files=[dict(name='local.bag',size=len(bag))]))
                path='/imports/chunk/'+created['id']+'/0/0'
                with self.assertRaises(urllib.error.HTTPError):post(path,bag,token='invalid')
                self.assertEqual(m.active['files'][0]['offset'],0)
                result=post(path,bag);self.assertEqual(result['offset'],len(bag))
                result=post('/imports/finish',dict(id=created['id']))
                self.assertEqual((Path(result['path'])/'camera.bag').read_bytes(),bag)
            finally:server.shutdown();server.server_close();thread.join()
