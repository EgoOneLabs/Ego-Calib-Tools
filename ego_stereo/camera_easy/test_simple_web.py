from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'),'Node required for UI event checks')
class SimpleWebTests(unittest.TestCase):
    def run_node(self,code):
        result=subprocess.run(['node','-e',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_joint_start_requires_two_files_and_requests_automatic_calculation(self):
        html=Path(__file__).with_name('web.html').read_text()
        callback=html.split("$('start').onclick=",1)[1].split('\nfunction durationFields',1)[0]
        setup=r'''
const assert=require('node:assert/strict'),nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,{value:'1',textContent:''});return nodes.get(id);};
$('mode').value='camera_imu';$('device_id').value='2UQ2';$('joint_seconds').value='90';
const selectedYaml=new Map();let submitted=null;
const post=async(path,value)=>{submitted={path,value};};
'''
        checks=r'''
(async()=>{
 await $('start').onclick();assert.equal(submitted,null);assert.ok($('error').textContent.includes('两个文件'));
 selectedYaml.set('joint_camera_file',{size:10,text:async()=>'camera-input'});
 selectedYaml.set('joint_imu_file',{size:10,text:async()=>'imu-input'});
 await $('start').onclick();assert.equal(submitted.path,'/start');
 assert.equal(submitted.value.camera_yaml,'camera-input');assert.equal(submitted.value.imu_yaml,'imu-input');
 assert.equal(submitted.value.auto_calculate,true);assert.equal(submitted.value.experimental_ack,true);
 $('workflow').value='existing';$('existing_dataset').value='record-id';
 for(const mode of ['camera','imu']){
  $('mode').value=mode;submitted=null;await $('start').onclick();
  assert.equal(submitted.path,'/offline/start');assert.equal(submitted.value.action,mode);
  assert.equal(submitted.value.dataset,'record-id');assert.equal(submitted.value.camera_yaml,undefined);
  assert.equal(submitted.value.imu_yaml,undefined);
 }
 $('mode').value='camera_imu';await $('start').onclick();assert.equal(submitted.value.action,'calibrate');
 assert.equal(submitted.value.camera_yaml,'camera-input');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        self.run_node(setup+"$('start').onclick="+callback+checks)

    def test_delayed_previous_device_defaults_cannot_replace_current_device(self):
        setup=r'''
const assert=require('node:assert/strict'),nodes=new Map();
const get=id=>{if(!nodes.has(id))nodes.set(id,{value:'',disabled:false,textContent:'',addEventListener(name,handler){this[name]=handler;}});return nodes.get(id);};
const document={getElementById:get};const selectedYaml=new Map(),window={egoOfflineBusy:false};
get('mode').value='camera_imu';get('device_id').value='2UQ2';
const pending=[];const fetch=path=>new Promise(resolve=>pending.push({path,resolve}));const post=()=>{};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
'''
        checks=r'''
(async()=>{
 assert.equal(pending.length,1);
 assert.equal(get('offline_panel').hidden,false);assert.equal(get('offline_panel').open,false);
 get('offline_panel').open=true;get('mode').value='imu';get('mode').onchange();
 assert.equal(get('offline_panel').hidden,true);assert.equal(get('offline_panel').open,false);
 get('mode').value='camera';get('mode').onchange();assert.equal(get('offline_panel').hidden,true);
 get('mode').value='camera_imu';get('mode').onchange();assert.equal(get('offline_panel').hidden,false);
 assert.equal(get('offline_panel').open,false);
 // Resolve all earlier requests before checking stale device defaults.
 for(const item of pending)item.resolve({ok:true,json:async()=>({})});await tick();pending.length=0;
 get('mode').onchange();assert.equal(pending.length,1);
 get('device_id').value='OTHER';get('device_id').change();assert.equal(pending.length,2);
 const result=name=>({ok:true,json:async()=>({camera:{name,path:'/data/'+name,text:name}})});
 pending[1].resolve(result('current.yaml'));await tick();
 pending[0].resolve(result('previous.yaml'));await tick();
 assert.equal(selectedYaml.get('joint_camera_file').name,'current.yaml');
 assert.equal(await selectedYaml.get('joint_camera_file').text(),'current.yaml');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        self.run_node(setup+Path(__file__).with_name('flow.js').read_text()+checks)
