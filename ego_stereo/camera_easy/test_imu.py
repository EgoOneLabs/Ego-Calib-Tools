import csv
import ctypes
import json
import math
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np
from imu_capture import Continuity, Query, capture, decode_packet
from imu_analysis import allan_segments, analyze, fit_region


def packet(start):
    return b''.join(struct.pack('>2sI6h',b'\xde\xc8',(start+i*32)%2**32,0,0,4096,-32768,32767,0) for i in range(14))


class ImuTests(unittest.TestCase):
    def test_parser_signed_endian_wrap_and_bad_protocol_rejected(self):
        data=packet(2**32-224)
        rows=decode_packet(data)
        self.assertEqual(len(rows),14)
        self.assertEqual(rows[7][0],0)
        self.assertEqual(rows[0][3:],(4096,-32768,32767,0))
        for bad in (data[:-1],b'xx'+data[2:],data[:18]+data[:18]+data[36:]):
            with self.assertRaises(ValueError):decode_packet(bad)
        self.assertEqual(ctypes.sizeof(Query),16)
        self.assertEqual(Query.size.offset,4)
        self.assertEqual(Query.data.offset,8)

    def test_duplicate_overlap_missing_samples_wrap_and_reset(self):
        c=Continuity()
        self.assertEqual(c.accept(2**32-32),(0,0))
        self.assertEqual(c.accept(0),(0,1))
        self.assertIsNone(c.accept(0))
        self.assertEqual(c.accept(96),(1,4))
        self.assertEqual(c.missing_estimated,2)
        self.assertEqual(c.duplicates,1)
        self.assertEqual(c.accept(1),(2,5))
        self.assertEqual(c.resets,1)

    def test_capture_keeps_raw_and_si_and_marks_early_stop(self):
        finish=threading.Event()
        class Reader:
            def __init__(self,device):self.n=0;self.closed=False
            def read(self):
                import time
                self.n+=1
                if self.n==10:finish.set()
                return packet((self.n-1)*448),time.monotonic_ns(),time.monotonic_ns()
            def close(self):self.closed=True
        with tempfile.TemporaryDirectory() as d:
            r=capture(d,'/dev/not-used',7200,threading.Event(),finish,lambda *a:None,Reader)
            self.assertEqual(r['status'],'CAPTURE_STOPPED_EARLY')
            self.assertEqual(r['samples'],140)
            self.assertEqual(Path(d,'imu_packets.bin').stat().st_size,2520)
            with Path(d,'imu_samples.csv').open() as f:rows=list(csv.DictReader(f))
            self.assertAlmostEqual(float(rows[0]['az_m_s2']),9.80665)
            self.assertFalse(r['quality_accepted'])
            self.assertNotIn('timestamp_ns',rows[0])

    def test_read_failure_flushes_and_preserves_abort_reason(self):
        class Broken:
            def __init__(self,*a):pass
            def read(self):raise OSError('unplugged')
            def close(self):pass
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'20'):
                capture(d,'x',60,threading.Event(),threading.Event(),lambda *a:None,Broken)
            report=json.loads(Path(d,'imu_capture.json').read_text())
            self.assertEqual(report['status'],'CAPTURE_ABORTED')
            self.assertEqual(report['errors'],20)
            self.assertIn('unplugged',report['error'])

    def test_allan_exact_difference_formula_never_bridges_gaps(self):
        a=np.arange(60,dtype=float).reshape(10,6)
        b=np.ones((10,6))*10000
        result=allan_segments([a,b],10,sizes=[1,2])
        for row,m in zip(result,[1,2]):
            terms=[]
            for v in (a,b):
                terms.extend([(v[i+m:i+2*m].mean(axis=0)-v[i:i+m].mean(axis=0))**2 for i in range(len(v)-2*m+1)])
            np.testing.assert_allclose(row[1:7],np.sqrt(np.mean(terms,axis=0)/2))
        self.assertEqual(result[0,-1],18)

    def test_white_noise_density_and_random_walk_fits(self):
        rng=np.random.default_rng(12);rate=100;density=.003
        noise=rng.normal(0,density*math.sqrt(rate),(100000,6))
        result=allan_segments([noise],rate,sizes=[1,2,4,8,16,32,64,128])
        np.testing.assert_allclose(result[:6,1]*np.sqrt(result[:6,0]),density,rtol=.08)
        tau=np.geomspace(.02,1000,50)
        self.assertAlmostEqual(fit_region(tau,.003/np.sqrt(tau),-.5,.02,2)['coefficient'],.003)
        self.assertAlmostEqual(fit_region(tau,.002*np.sqrt(tau/3),.5,10,1000)['coefficient'],.002)
        self.assertIsNone(fit_region(tau,np.ones_like(tau),.5,10,1000))

    def test_short_synthetic_recording_generates_report_not_final_yaml(self):
        import matplotlib
        matplotlib.use('Agg')
        rng=np.random.default_rng(8);n=12000;rate=200
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'imu_capture.json').write_text(json.dumps({'status':'CAPTURE_COMPLETED','elapsed_seconds':60,'counter_discontinuities':0}))
            with (root/'imu_samples.csv').open('w') as f:
                f.write(','.join('c'+str(i) for i in range(18))+'\n')
                for i in range(n):
                    axes=rng.normal(0,.001,6);axes[2]+=9.80665
                    row=[0,i,i*32,i//14,0,1000000000+(i//14)*70000000,*([0]*6),*axes]
                    f.write(','.join(map(str,row))+'\n')
            report=analyze(root)
            self.assertAlmostEqual(report['estimated_sample_rate_hz'],rate,places=4)
            self.assertFalse(report['ready_for_camera_imu'])
            self.assertTrue((root/'imu-report.pdf').read_bytes().startswith(b'%PDF'))
            self.assertTrue((root/'imu_small_review.tar.gz').is_file())
            self.assertFalse((root/'imu-candidate.yaml').exists())

    def test_unified_mode_rejects_unknown_mode_and_invalid_durations(self):
        from app import App
        app=App.__new__(App)
        with self.assertRaisesRegex(ValueError,'未知'):
            app.start({'mode':'unknown'})
        for invalid in (0,-1,59,86401,float('nan'),float('inf')):
            with self.assertRaisesRegex(ValueError,'录制时长'):
                app.start_imu({'device_id':'test','imu_seconds':invalid})

    def test_custom_durations_reach_capture_without_waiting(self):
        from app import App
        import time
        from types import SimpleNamespace
        for seconds in (120,1800,5400,9000):
            with tempfile.TemporaryDirectory() as d:
                app=App.__new__(App)
                app.lock=threading.RLock();app.imu_thread=None
                app.frame_ns=time.monotonic_ns();app.state={'stage':'READY'}
                app.data_root=Path(d);app.hardware={'device':'/dev/not-used'}
                app.end_capture=threading.Event();app.imu_cancel=threading.Event()
                with patch('app.threading.Thread') as thread, patch('app.shutil.disk_usage',return_value=SimpleNamespace(free=10**12)):
                    app.start_imu({'device_id':'test','imu_seconds':seconds})
                    self.assertEqual(thread.call_args.kwargs['args'][1],seconds)
                    self.assertEqual(app.state['duration'],seconds)
                    self.assertEqual(app.state['stage'],'IMU_RECORDING')
                    thread.return_value.start.assert_called_once()
