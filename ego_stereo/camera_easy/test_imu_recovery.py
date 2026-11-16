import csv
import json
from pathlib import Path
import struct
import tempfile
import unittest
import threading
import numpy as np
from imu_capture import Continuity, decode_packet, capture
from imu_recover import recover,replay_counters
from core import sha
from imu_analysis import fit_axis


class RecoveryTests(unittest.TestCase):
    def test_allan_long_tau_uses_support_across_complete_segments(self):
        from imu_analysis import allan_segments
        pieces=[np.zeros((1000,6)),np.ones((1000,6))*10000]*20
        result=allan_segments(pieces,100)
        self.assertGreater(result[-1,0],1)
        self.assertTrue(np.all(result[:,1:7]==0))
        for row in result:
            m=round(row[0]*100)
            self.assertGreaterEqual(sum(max(0,len(v)//m-1) for v in pieces),20)

    def test_noise_fit_follows_measured_branches_without_forcing_missing_term(self):
        tau=np.geomspace(.02,100,60)
        # A filtered sensor may exhibit a white-noise slope only above 2s.
        dev=np.where(tau<2,.001,np.where(tau<20,.001*np.sqrt(2/tau),.001*np.sqrt(2/20)))
        fitted=fit_axis(tau,dev)
        self.assertIsNotNone(fitted['white_noise'])
        self.assertIsNone(fitted['bias_random_walk'])
        self.assertGreater(fitted['white_noise']['tau_range_s'][0],1)

    def test_rejected_packet_preserved_separately(self):
        stop=threading.Event();finish=threading.Event()
        class Reader:
            def __init__(self,*a):self.n=0
            def read(self):
                self.n+=1
                if self.n==1:return b'x'*252,1,2
                if self.n==11:finish.set()
                raw=b''.join(struct.pack('>2sI6h',b'\xde\xc8',((self.n-2)*14+i)*32,0,0,4096,0,0,0) for i in range(14))
                return raw,self.n*100,self.n*100+1
            def close(self):pass
        with tempfile.TemporaryDirectory() as d:
            result=capture(d,'unused',60,stop,finish,lambda *a:None,Reader)
            self.assertEqual(result['errors'],1)
            self.assertEqual(Path(d,'imu_rejected_packets.bin').read_bytes(),b'x'*252)
            with Path(d,'imu_requests.csv').open() as f:rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]['rejected_offset'],'0')

    def test_packet_accepts_observed_u24_wrap(self):
        start=2**24-193
        raw=b''.join(struct.pack('>2sI6h',b'\xde\xc8',(start+i*32)%2**24,0,0,4096,0,0,0) for i in range(14))
        rows=decode_packet(raw)
        self.assertEqual(len(rows),14)
        self.assertTrue(any(b[0]<a[0] for a,b in zip(rows,rows[1:])))

    def test_stream_u24_wrap_and_missing_packet_preserve_real_reset(self):
        c=Continuity()
        c.accept(16776895)
        self.assertEqual(c.accept(159),(1,15))
        self.assertEqual(c.wraps24,1)
        self.assertEqual(c.resets,0)
        self.assertEqual(c.missing_estimated,14)
        c.accept(191)
        c.accept(42)
        self.assertEqual(c.resets,1)

    def test_replay_counts_missing_without_filling_unknown_jump(self):
        t,s,r=replay_counters(np.r_[np.arange(100)*32+16773567,np.arange(100)*32+16776767]%(2**24))
        self.assertEqual(r['counter_wraps_24bit'],1)
        self.assertEqual(r['counter_discontinuities'],0)
        self.assertEqual(len(t),200)
        counters=np.arange(200)*32
        counters[100:]-=123
        with self.assertRaisesRegex(ValueError,'无法解释'):replay_counters(counters)

    def test_raw_reanalysis_writes_only_new_directory_and_checks_hash(self):
        rng=np.random.default_rng(34);n=14000
        dtype=np.dtype([('magic','S2'),('counter','>u4'),('axes','>i2',(6,))])
        raw=np.empty(n,dtype=dtype);raw['magic']=b'\xde\xc8'
        raw['counter']=(np.arange(n)*32+2**24-193)%(2**24)
        raw['axes']=rng.normal(0,2,(n,6)).astype(np.int16);raw['axes'][:,2]+=4096
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'original';root.mkdir()
            raw.tofile(root/'imu_packets.bin')
            original={'status':'CAPTURE_COMPLETED','samples':n,'duplicates':0,'counter_discontinuities':1,'errors':0,'elapsed_seconds':70}
            (root/'imu_capture.json').write_text(json.dumps(original))
            with (root/'imu_requests.csv').open('w',newline='') as f:
                w=csv.writer(f);w.writerow(['phase','valid','unique_samples','host_after_ns'])
                for i in range(n//14):w.writerow(['record','True',14,1000000000+i*70000000])
            before={p.name:p.read_bytes() for p in root.iterdir()}
            with self.assertRaisesRegex(ValueError,'不匹配'):recover(root,{'imu_packets.bin':'wrong'},notify=lambda *a:None)
            out,report=recover(root,{'imu_packets.bin':sha(root/'imu_packets.bin')},notify=lambda *a:None)
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})
            self.assertNotEqual(root,out)
            meta=json.loads((out/'imu_capture.json').read_text())
            self.assertEqual(meta['counter_discontinuities'],0)
            self.assertEqual(meta['counter_wraps_24bit'],1)
            self.assertEqual(report['samples'],n)
            self.assertFalse(report['quality_accepted'])
            self.assertTrue((out/'imu-report.pdf').is_file())
            self.assertTrue((out/'imu_small_review.tar.gz').is_file())
