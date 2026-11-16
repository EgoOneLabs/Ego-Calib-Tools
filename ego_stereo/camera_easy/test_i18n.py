"""UI-language checks without a camera, Docker or a browser runtime."""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent

class Texts(HTMLParser):
    def __init__(self):
        super().__init__(); self.tag = ''; self.texts = []
    def handle_starttag(self, tag, attrs):
        self.tag = tag
    def handle_data(self, data):
        if self.tag not in ('script', 'style') and re.search('[\u4e00-\u9fff]', data):
            self.texts.append(data.strip())

class LanguageTests(unittest.TestCase):
    def test_all_static_ui_text_has_an_english_translation(self):
        dictionary = json.loads((ROOT / 'i18n.json').read_text())
        for name in ('web.html', 'offline.html'):
            parser = Texts(); parser.feed((ROOT / name).read_text())
            for text in parser.texts:
                if text == '中文':
                    continue  # The English UI offers a Chinese-language switch.
                self.assertIn(text, dictionary)
                self.assertFalse(re.search('[\u4e00-\u9fff]', dictionary[text]))

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_english_default_saved_chinese_and_switch_without_reload(self):
        script = (ROOT / 'i18n.js').read_text()
        catalog = (ROOT / 'i18n.json').read_text()
        setup = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
function run(saved){
 const handlers={},store=new Map(saved?[['ego-calibration-language',saved]]:[]);
 const button={textContent:'',setAttribute(){}};
 const document={documentElement:{},title:'',body:{querySelectorAll:()=>[]},
 getElementById:()=>button,querySelector:()=>({}),
 createTreeWalker:()=>({nextNode:()=>false})};
 let updates=0;
 const context={document,NodeFilter:{SHOW_TEXT:4},WeakMap,Object,
 localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},
 MutationObserver:class{observe(){}},update:()=>updates++,selectMode:()=>updates++};
 context.window={egoTranslations:CATALOG,addEventListener:(n,f)=>handlers[n]=f};
 vm.createContext(context);vm.runInContext(SCRIPT,context);handlers.DOMContentLoaded();
 return {context,button,store,updates:()=>updates};
}
let state=run();assert.equal(state.context.window.egoI18n.english(),true);
assert.equal(state.context.document.title,'Headband Calibration Tool');
assert.equal(state.context.window.egoI18n.t('/data/用户/imu.yaml'),'/data/用户/imu.yaml');
state.button.onclick();assert.equal(state.context.window.egoI18n.english(),false);
assert.equal(state.context.document.title,'头环标定工具');
assert.equal(state.store.get('ego-calibration-language'),'zh');
assert.equal(state.updates(),2); // Re-render in place; no location/reload API exists.
state.button.onclick();assert.equal(state.context.window.egoI18n.english(),true);
assert.equal(run('zh').context.window.egoI18n.english(),false);
'''
        code = 'const CATALOG=' + catalog + '; const SCRIPT=' + json.dumps(script) + ';\n' + setup
        result = subprocess.run(['node', '-e', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == '__main__':
    unittest.main()
