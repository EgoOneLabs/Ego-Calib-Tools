from pathlib import Path
import shutil
import subprocess
import unittest


class OfflineWebTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required for DOM event checks')
    def test_file_inputs_submit_correct_action_and_block_changes_when_busy(self):
        setup=r'''
const assert=require('node:assert/strict');
const nodes=new Map();
class Node{
 constructor(){this.value='';this.disabled=false;this.files=[];this.children=[];this.textContent='';this.style={};this.classList={add(){},remove(){}};}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=[...items];}
 get options(){return this.children;}
 setAttribute(){}
 click(){if(this.onclick)this.onclick();}
}
const get=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
const document={getElementById:get,createElement:()=>new Node()};
const window={};const token='test-token';
const Option=function(text,value){const n=new Node();n.textContent=text;n.value=value;return n;};
get('off_action').value='calibrate';
const timers=[];const setInterval=f=>timers.push(f);
let busy=false,submitted=null;
const fetch=async(path,options)=>{
 let data={};
 if(path==='/offline/catalog')data={ready:true,root:'/data',datasets:[{id:'record',kind:'prepared',path:'/data/camera_imu/2UQ2/input'}],parameters:[]};
 if(path==='/offline/state')data={busy,message:'Ready',files:[],logs:[],output:''};
 if(path==='/state')data={stage:'READY'};
 if(path==='/offline/start'){submitted=JSON.parse(options.body);assert.equal(options.headers['X-Ego-Token'],token);busy=true;}
 return {ok:true,json:async()=>data};
};
const tick=()=>new Promise(r=>setTimeout(r,0));
'''
        checks=r'''
(async()=>{
 await tick();get('off_dataset').value='record';get('off_action').value='validate';get('off_action').onchange();
 const drop=(id,files)=>get(id+'_drop').ondrop({preventDefault(){},stopPropagation(){},dataTransfer:{files}});
 drop('off_candidate',[{name:'<candidate>.yaml',size:10,text:async()=>'candidate-text'}]);
 drop('off_imu',[{name:'imu.yml',size:10,text:async()=>'imu-text'}]);await tick();
 assert.equal(get('off_candidate_name').textContent,'<candidate>.yaml');
 drop('off_candidate',[{name:'bad.zip',size:10,text:async()=>'bad'}]);await tick();
 assert.ok(get('off_error').textContent);assert.equal(get('off_candidate_name').textContent,'<candidate>.yaml');
 get('off_ack').checked=true;get('off_ack').onchange();assert.equal(get('off_start').disabled,false);
 await get('off_start').onclick();assert.equal(submitted.action,'validate');assert.equal(submitted.candidate_yaml,'candidate-text');assert.equal(submitted.imu_yaml,'imu-text');assert.equal(submitted.experimental_ack,true);
 await timers[0]();assert.equal(get('off_start').disabled,true);
 drop('off_candidate',[{name:'changed.yaml',size:10,text:async()=>'changed'}]);await tick();
 assert.equal(get('off_candidate_name').textContent,'<candidate>.yaml');assert.equal(window.egoOfflineBusy,true);
 console.log('DOM event workflow passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',"global.egoI18n={t:x=>x,english:()=>false};\n"+setup+Path(__file__).with_name('offline.js').read_text()+checks],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
