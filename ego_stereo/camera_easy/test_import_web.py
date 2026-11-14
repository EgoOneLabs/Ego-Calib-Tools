from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'),'Node required for upload event checks')
class ImportWebTests(unittest.TestCase):
    def test_native_file_selection_streams_authenticated_chunks_and_selects_import(self):
        setup=r'''
const assert=require('node:assert/strict'),nodes=new Map();
class Node{constructor(){this.value='';this.files=[];this.disabled=false;this.classList={add(){},remove(){}};this.children=[];}setAttribute(){}append(n){this.children.push(n);}replaceChildren(...n){this.children=n;}click(){if(this.onclick)this.onclick();}}
const get=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
const document={getElementById:get},window={},token='test-token';
const Option=function(text,value){const n=new Node();n.value=value;return n;};
get('mode').value='camera';get('workflow').value='existing';for(const k of ['rows','cols'])get(k).value='6';get('tag_mm').value='88';get('gap_mm').value='26.4';
let imported=false;const chunks=[];let sent=null;
const fetch=async(path,options={})=>{
 let data={};
 if(path==='/offline/catalog')data={datasets:imported?[{id:'import-id',mode:'camera',path:'/data/imports/camera/record'}]:[]};
 else if(path==='/imports/create'){sent=JSON.parse(options.body);assert.equal(options.headers['X-Ego-Token'],token);data={id:'session',chunk_bytes:2};}
 else if(path.startsWith('/imports/chunk/')){assert.equal(options.headers['X-Ego-Token'],token);chunks.push({path,body:options.body});data={offset:chunks.length*2};}
 else if(path==='/imports/finish'){imported=true;data={id:'import-id',path:'/data/imports/camera/record'};}
 else throw Error('Unexpected request '+path);
 return {ok:true,json:async()=>data};
};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
'''
        checks=r'''
(async()=>{
 await tick();
 const file={name:'camera-local.bag',size:5,slice:(a,b)=>({start:a,end:b})};get('existing_files').files=[file];
 get('existing_files').onchange();
 for(let i=0;i<20&&get('existing_dataset').value!=='import-id';i++)await tick();
 assert.equal(sent.mode,'camera');assert.deepEqual(sent.files,[{name:'camera-local.bag',size:5}]);
 assert.equal(chunks.length,3);assert.deepEqual(chunks.map(c=>c.body),[{start:0,end:2},{start:2,end:4},{start:4,end:5}]);
 assert.equal(get('existing_dataset').value,'import-id');assert.equal(window.egoImportBusy,false);
 assert.ok(get('existing_import_status').textContent.includes('开始计算'));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',setup+Path(__file__).with_name('existing.js').read_text()+checks],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
