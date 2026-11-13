"""Container startup regression: shell ENTRYPOINT must not swallow the keepalive."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from environment import Docker

class FakeDocker(Docker):
    def __init__(self, root, existing=False, dies=False):
        super().__init__(); self.root=root; self.present=existing; self.running=False
        self.dies=dies; self.commands=[]; self.created=None
    def exists(self,*args):
        if args[0]=='image': return True
        return self.present and args[-1]=='ego-camera-kalibr'
    def run(self,*args,**kw):
        self.commands.append(args)
        if args[0]=='create':
            self.created=args; self.present=True
            # Model the reported image: CMD alone does not replace ENTRYPOINT.
            self.safe='--entrypoint' in args and args[args.index('--entrypoint')+1]=='/bin/sleep'
        if args[0]=='start': self.running=getattr(self,'safe',False) and not self.dies
        if args[0]=='inspect':
            return json.dumps([{'Image':'fixture','State':{'Running':self.running},
              'Mounts':[{'Type':'bind','RW':True,'Destination':'/data','Source':str(self.root)}]}])
        if args[0]=='exec' and not self.running: raise AssertionError('exec into stopped container')
        return ''

class EnvironmentTests(unittest.TestCase):
    def test_overrides_shell_entrypoint_before_image(self):
        with tempfile.TemporaryDirectory() as d, patch('environment.Path.home',return_value=Path(d)):
            f=FakeDocker(Path(d)); name,root,info=f.prepare()
            a=f.created; self.assertLess(a.index('--entrypoint'),a.index('kalibr:noetic'))
            self.assertEqual(a[-2:],('kalibr:noetic','infinity'))
            self.assertTrue(info['State']['Running'])
    def test_stopped_legacy_container_does_not_proceed_to_exec(self):
        with tempfile.TemporaryDirectory() as d:
            f=FakeDocker(Path(d),existing=True)
            with self.assertRaisesRegex(ValueError,'启动后立即退出'): f.prepare()
            self.assertFalse(any(a[0]=='exec' for a in f.commands))
            self.assertFalse(any(a[0] in ('rm','rename') for a in f.commands))
    def test_new_container_exit_is_reported(self):
        with tempfile.TemporaryDirectory() as d, patch('environment.Path.home',return_value=Path(d)):
            f=FakeDocker(Path(d),dies=True)
            with self.assertRaisesRegex(ValueError,'启动后立即退出'): f.prepare()

if __name__=='__main__':unittest.main()
