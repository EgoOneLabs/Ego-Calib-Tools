from pathlib import Path
import shutil
import subprocess
import unittest


class YamlDropTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for UI event checks')
    def test_drop_picker_validation_busy_clear_and_safe_filename(self):
        html=Path(__file__).with_name('web.html').read_text()
        code=html.split('// YAML_DROP_BEGIN',1)[1].split('// YAML_DROP_END',1)[0]
        setup=r'''
const assert=require('node:assert/strict');
const nodes=new Map();const $=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,value:'',files:[],textContent:'',classList:{add(){},remove(){}},click(){this.clicks=(this.clicks||0)+1;}});return nodes.get(id);};
const window={addEventListener(){}};
'''
        checks=r'''
const id='joint_camera_file',zone=$(id+'_drop'),input=$(id);
let prevented=0;
const drop=files=>zone.ondrop({preventDefault(){prevented++;},stopPropagation(){},dataTransfer:{files}});
const a={name:'<camera>.yaml',size:32768,text:async()=>'cam0: {}'};
drop([a]);assert.equal(selectedYaml.get(id),a);
assert.ok($(id+'_status').textContent.includes(a.name));
for(const invalid of [{name:'x.zip',size:10},{name:'x.yaml',size:0},{name:'x.yml',size:32769}]){
 drop([invalid]);assert.equal(selectedYaml.get(id),a);assert.ok($('error').textContent);
}
drop([a,a]);assert.equal(selectedYaml.get(id),a);
input.disabled=true;drop([{name:'new.yaml',size:10}]);$(id+'_clear').onclick();assert.equal(selectedYaml.get(id),a);
zone.onclick();assert.equal(input.clicks,undefined);
input.disabled=false;zone.onclick();assert.equal(input.clicks,1);
input.files=[{name:'picked.yml',size:12}];input.onchange();assert.equal(selectedYaml.get(id).name,'picked.yml');
$(id+'_clear').onclick();assert.equal(selectedYaml.has(id),false);assert.equal(input.value,'');
assert.equal($(id+'_clear').disabled,true);assert.ok(prevented>=5);
'''
        result=subprocess.run(['node','-e',"global.egoI18n={t:x=>x,english:()=>false};\n"+setup+code+checks],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
