/* UI translations only. Original logs, user inputs, file names and paths are preserved. */
(() => {
 const dictionary=window.egoTranslations;
 let language='en';
 try { language=localStorage.getItem('ego-calibration-language')==='zh'?'zh':'en'; } catch (_) {}
 const reverse=Object.fromEntries(Object.entries(dictionary).map(([zh,en])=>[en,zh]));
 const original=new WeakMap();
 const attributes=new WeakMap();
 const english=()=>language==='en';
 const t=value=>english()?(dictionary[value]??value):value;
 window.egoI18n={english,t};
 function translate(root){
  for(const element of root.querySelectorAll?.("[aria-label],[title],[alt]")||[]){
   let saved=attributes.get(element);if(!saved){saved={};for(const key of ["aria-label","title","alt"]){const v=element.getAttribute(key);if(v in dictionary)saved[key]=v;else if(v in reverse)saved[key]=reverse[v];}attributes.set(element,saved);}
   for(const [key,value] of Object.entries(saved))element.setAttribute(key,t(value));
  }
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  const nodes=[]; while(walker.nextNode())nodes.push(walker.currentNode);
  for(const node of nodes){
   if(node.parentElement.closest('script,style,pre,input,textarea,#language_toggle'))continue;
   let base=original.get(node);
   if(base===undefined){const raw=node.textContent;const key=raw.trim();if(key in dictionary)base=raw;else if(key in reverse)base=raw.replace(key,reverse[key]);else continue;original.set(node,base);}
   // Only exact static UI text is translated; dynamic user-provided strings are not.
   const value=english()?base.replace(base.trim(),dictionary[base.trim()]):base;
   if(node.textContent!==value)node.textContent=value;
  }
 }
 function refresh(){
  document.documentElement.lang=english()?'en':'zh-CN';
  document.title=t('头环标定工具');
  const button=document.getElementById('language_toggle');
  button.textContent=english()?'中文':'English';button.setAttribute('aria-label',english()?'Switch to Chinese':'切换到英文');
  translate(document.body);
 }
 window.addEventListener('DOMContentLoaded',()=>{
  const button=document.getElementById('language_toggle');
  button.onclick=()=>{
   language=english()?'zh':'en';try{localStorage.setItem('ego-calibration-language',language);}catch(_){}
   refresh();
   // Re-render labels without reloading or interrupting active recordings.
   if(typeof selectMode==='function')selectMode();
   if(typeof update==='function')update();
  };
  refresh();
  new MutationObserver(records=>{for(const r of records){
   // Backend-generated diagnostics and raw logs may remain in their original language.
   if(r.type==='childList')translate(r.target);
  }}).observe(document.querySelector('main'),{childList:true,subtree:true});
 });
})();
