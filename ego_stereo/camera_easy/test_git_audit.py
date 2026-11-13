"""Exercise audit commands against Git's actual ownership safety check."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

class GitAuditTests(unittest.TestCase):
    def test_scoped_trust_reads_version_without_changing_global_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo=root/'repo';subprocess.run(['git','init','-q',str(repo)],check=True)
            subprocess.run(['git','-C',str(repo),'-c','user.name=Blue88ight','-c','user.email=208805960+Blue88ight@users.noreply.github.com','commit','-q','--allow-empty','-m','fixture'],check=True)
            env=dict(os.environ,GIT_TEST_ASSUME_DIFFERENT_OWNER='1',GIT_CONFIG_GLOBAL=str(root/'global'),GIT_CONFIG_NOSYSTEM='1')
            result=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('dubious ownership',result.stderr)
            lines=Path(__file__).with_name('pipeline.py').read_text().splitlines()
            commands=[line for line in lines if line.startswith('git ')]
            self.assertEqual(len(commands),3)
            for line in commands:
                argv=shlex.split(line.split(' > ')[0])
                argv=[a.replace('/catkin_ws/src/kalibr',str(repo)) for a in argv]
                result=subprocess.run(argv,env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((root/'global').exists())

if __name__=='__main__':unittest.main()
