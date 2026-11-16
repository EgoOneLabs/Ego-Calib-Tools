"""Real-process regression for detached session leaders, without Docker or cameras."""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile,threading,time,unittest
from unittest.mock import patch
from pipeline import logged_run

@unittest.skipUnless(shutil.which('setsid') and hasattr(os,'setpgrp'),'POSIX setsid required')
class ProcessWaitTests(unittest.TestCase):
    def test_group_leader_waits_and_propagates_success_and_failure(self):
        original=subprocess.Popen
        for code in (0,7):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);lines=[]
                command=['setsid','--wait',sys.executable,'-u','-c',
                         'import time,sys; print("started"); time.sleep(0.2); print("finished"); sys.exit('+str(code)+')']
                def leader(*args,**kwargs):
                    return original(*args,preexec_fn=os.setpgrp,**kwargs)
                started=time.monotonic()
                with patch('pipeline.subprocess.Popen',side_effect=leader):
                    if code:
                        with self.assertRaisesRegex(ValueError,'calibration.log'):
                            logged_run(command,root,'calibration.log',threading.Event(),lines.append)
                    else:
                        logged_run(command,root,'calibration.log',threading.Event(),lines.append)
                self.assertGreaterEqual(time.monotonic()-started,0.18)
                self.assertEqual(lines,['started','finished'])
                result=json.loads((root/'calibration.log.process.json').read_text())
                self.assertEqual(result['returncode'],code)
                self.assertTrue(result['session_wait_requested'])

if __name__=='__main__':unittest.main()
