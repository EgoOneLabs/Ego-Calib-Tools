/* Browser-local file/folder selection and bounded uploads to the local App. */
(() => {
 const el=id=>document.getElementById(id);let generation=0,catalog=null,cancelled=false,controller=null;
 const mode=el('mode'),workflow=el('workflow'),select=el('existing_dataset');
 window.egoImportBusy=false;
 const busy=()=>window.egoImportBusy||window.egoOfflineBusy||select.disabled;
 async function request(path,value,signal){
  const response=await fetch(path,{method:'POST',headers:{'X-Ego-Token':token,'Content-Type':'application/json'},body:JSON.stringify(value),signal});
  const data=await response.json();if(!response.ok)throw Error(data.error||egoI18n.t('导入请求失败'));return data;
 }
 function showSource(){
  const item=catalog?.datasets.find(p=>p.id===select.value);
  el('existing_source').textContent=item?egoI18n.t('已选择：')+item.path:'';
 }
 async function refresh(){
  const seq=++generation,kind=mode.value;
  if(workflow.value!=='existing')return;
  try{
   const response=await fetch('/offline/catalog'),data=await response.json();
   if(!response.ok)throw Error(data.error||egoI18n.t('无法读取录制列表'));
   if(seq!==generation||mode.value!==kind||workflow.value!=='existing')return;
   catalog=data;const old=select.value;
   const items=data.datasets.filter(p=>(p.mode||'camera_imu')===kind);
   select.replaceChildren(new Option(items.length?egoI18n.t('也可选择本机已有录制'):egoI18n.t('列表暂无录制，可直接在上方拖入或选择文件'),''));
   for(const p of items)select.append(new Option(p.path,p.id));
   if(items.some(p=>p.id===old))select.value=old;
   showSource();
  }catch(e){el('existing_source').textContent=e.message;}
 }
 function change(){
  el('existing_options').hidden=workflow.value!=='existing';
  el('existing_hint').textContent=mode.value==='camera'?egoI18n.t('拖入一个相机 BAG，或点击选择本地文件。可同时选 aprilgrid.yaml；没有板配置时使用下方实测尺寸。不需要 IMU 文件。'):mode.value==='imu'?egoI18n.t('选齐 imu_samples.csv 和 imu_capture.json，或拖入/选择完整静止录制文件夹。不需要相机参数；当前不支持任意 IMU BAG。'):egoI18n.t('拖入一个联合 BAG，或选择完整联合录制文件夹（图像、CSV 与元数据）。然后在下方两个框导入 Camera 和 IMU 参数。');
  el('existing_files').accept=mode.value==='imu'?'.csv,.json':'.bag,.yaml,.yml';
  el('existing_drop_title').textContent=mode.value==='camera'?egoI18n.t('拖入相机 BAG，或点击选择文件'):mode.value==='imu'?egoI18n.t('拖入 IMU 数据文件或录制文件夹'):egoI18n.t('拖入联合 BAG 或完整录制文件夹');
  refresh();
 }
 function status(text){el('existing_import_status').textContent=text;}
 function setBusy(value){
  window.egoImportBusy=value;
  for(const id of ['existing_files','existing_folder','existing_choose','existing_folder_choose'])el(id).disabled=value;
  el('existing_cancel').hidden=!value;el('existing_import_progress').hidden=!value;
  el('existing_drop').setAttribute('aria-disabled',String(value));
 }
 async function importFiles(entries){
  let id=null;cancelled=false;setBusy(true);el('existing_import_error').textContent='';
  try{
   const files=entries.filter(x=>!x.name.split('/').some(part=>part.startsWith('.')));
   if(!files.length||files.length>20000)throw Error(egoI18n.t('请选择文件或录制文件夹，最多 20000 个文件'));
   const modeValue=mode.value;
   const board=Object.fromEntries(['rows','cols','tag_mm','gap_mm'].map(k=>[k,Number(el(k).value)]));
   status(egoI18n.t('正在准备本地导入…'));
   const created=await request('/imports/create',{mode:modeValue,board,files:files.map(x=>({name:x.name,size:x.file.size}))});id=created.id;
   let done=0;const total=files.reduce((n,x)=>n+x.file.size,0);el('existing_import_progress').max=total;
   for(let index=0;index<files.length;index++){
    const {file,name}=files[index];let offset=0;
    while(offset<file.size){
     if(cancelled)throw Error(egoI18n.t('已取消导入；原文件未改动'));
     controller=new AbortController();const end=Math.min(file.size,offset+created.chunk_bytes);
     const response=await fetch('/imports/chunk/'+id+'/'+index+'/'+offset,{method:'POST',headers:{'X-Ego-Token':token},body:file.slice(offset,end),signal:controller.signal});
     const data=await response.json();if(!response.ok)throw Error(data.error||egoI18n.t('文件导入失败'));
     done+=end-offset;offset=end;el('existing_import_progress').value=done;
     status(egoI18n.t('正在导入 ')+(index+1)+'/'+files.length+'：'+name+' · '+(done/total*100).toFixed(1)+'%');
    }
   }
   if(cancelled)throw Error(egoI18n.t('已取消导入；原文件未改动'));
   status(egoI18n.t('文件已传完，正在检查格式和所需文件…'));
   const result=await request('/imports/finish',{id});id=null;
   await refresh();select.value=result.id;showSource();
   status(egoI18n.t('已导入并选中，可以点击“开始计算”。原文件保留。'));
  }catch(e){
   el('existing_import_error').textContent=cancelled?egoI18n.t('已取消导入；原文件未改动'):e.message;
   status(egoI18n.t('尚未导入成功，请按提示补齐后重新选择。'));
  }finally{
   if(id)try{await request('/imports/abort',{id});}catch(e){el('existing_import_error').textContent+=egoI18n.t('；请重启工具后重新导入。');}
   controller=null;setBusy(false);
  }
 }
 function picked(input){if(busy()||!input.files.length)return;importFiles(Array.from(input.files,x=>({file:x,name:x.webkitRelativePath||x.name})));input.value='';}
 const zone=el('existing_drop');
 el('existing_files').onchange=()=>picked(el('existing_files'));
 el('existing_folder').onchange=()=>picked(el('existing_folder'));
 el('existing_choose').onclick=()=>{if(!busy())el('existing_files').click();};
 el('existing_folder_choose').onclick=()=>{if(!busy())el('existing_folder').click();};
 zone.onclick=()=>{if(!busy())el('existing_files').click();};
 zone.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();zone.click();}};
 zone.ondragover=e=>{e.preventDefault();if(!busy())zone.classList.add('drag-over');};
 zone.ondragleave=()=>zone.classList.remove('drag-over');
 async function walk(entry,prefix,files){
  if(cancelled)throw Error(egoI18n.t('已取消'));
  if(files.length>=20000)throw Error(egoI18n.t('文件超过 20000 个，请选择单次录制目录'));
  if(entry.name.startsWith('.'))return;
  if(entry.isFile){const file=await new Promise((resolve,reject)=>entry.file(resolve,reject));files.push({file,name:prefix+entry.name});return;}
  if(entry.isDirectory){const reader=entry.createReader();let batch;
   do{batch=await new Promise((resolve,reject)=>reader.readEntries(resolve,reject));for(const child of batch)await walk(child,prefix+entry.name+'/',files);}while(batch.length);
  }
 }
 zone.ondrop=async e=>{
  e.preventDefault();e.stopPropagation();zone.classList.remove('drag-over');if(busy())return;
  const entries=Array.from(e.dataTransfer.items||[],x=>x.webkitGetAsEntry?.()).filter(Boolean);
  const fallback=Array.from(e.dataTransfer.files||[],file=>({file,name:file.name}));
  if(!entries.length){importFiles(fallback);return;}
  cancelled=false;setBusy(true);status(egoI18n.t('正在读取拖入的文件列表…'));
  try{const files=[];for(const entry of entries)await walk(entry,'',files);if(!cancelled)await importFiles(files);}
  catch(error){el('existing_import_error').textContent=cancelled?egoI18n.t('已取消导入'):error.message;}
  finally{if(!controller)setBusy(false);}
 };
 el('existing_cancel').onclick=()=>{cancelled=true;controller?.abort();};
 const modeChange=mode.onchange;mode.onchange=()=>{if(modeChange)modeChange();select.value='';change();};
 const workflowChange=workflow.onchange;workflow.onchange=()=>{if(workflowChange)workflowChange();change();};
 select.onchange=showSource;el('existing_refresh').onclick=refresh;change();
})();
