/* Existing-data workflow; large BAG/images stay on the local data disk. */
(() => {
 const el=id=>document.getElementById(id), values=new Map();
 let catalog=null, busy=false, appBusy=false, refreshing=false, parametersLoading=0;
 window.egoOfflineBusy=false;
 async function request(path,body){
  const options=body===undefined?{}:{method:'POST',headers:{'X-Ego-Token':token,'Content-Type':'application/json'},body:JSON.stringify(body)};
  const response=await fetch(path,options), data=await response.json();
  if(!response.ok)throw Error(data.error||egoI18n.t('请求失败'));return data;
 }
 function controls(){
  const action=el('off_action').value, candidate=action==='validate';
  el('off_camera_group').hidden=candidate;el('off_candidate_group').hidden=!candidate;
  el('off_start').textContent=candidate?egoI18n.t('开始验证'):egoI18n.t('开始联合计算');
  el('off_explanation').textContent=candidate?egoI18n.t('固定所选联合外参与时间偏移，只拟合本段运动轨迹、重力方向和 IMU 偏置，再报告误差；不是重新标定，也不是完全开环预测。'):egoI18n.t('自动准备并核对 BAG，再调用 Kalibr 求解；将生成联合外参 YAML、PDF 报告和 TXT 摘要。');
  for(const id of ['off_action','off_dataset','off_refresh','off_ack','off_camera','off_candidate','off_imu','off_camera_recent','off_candidate_recent','off_imu_recent'])el(id).disabled=busy||appBusy;
  for(const id of ['off_camera','off_candidate','off_imu']){
   el(id+'_drop').setAttribute('aria-disabled',String(busy||appBusy));el(id+'_drop').tabIndex=busy||appBusy?-1:0;
  }
  el('off_start').disabled=busy||appBusy||parametersLoading>0||!el('off_dataset').value||!el('off_ack').checked||!values.get(candidate?'off_candidate':'off_camera')||!values.get('off_imu');
  el('off_stop').disabled=!busy;
 }
 for(const id of ['off_camera','off_candidate','off_imu']){
  const input=el(id),zone=el(id+'_drop');let generation=0;
  async function accept(files){
   if(busy||appBusy)return;
   if(files.length!==1){el('off_error').textContent=egoI18n.t('每个区域请只放一个 YAML 文件');return;}
   const f=files[0];if(!/\.ya?ml$/i.test(f.name)||!f.size||f.size>32768){el('off_error').textContent=egoI18n.t('请选择非空 YAML 文件，最大 32 KiB');return;}
   const seq=++generation;parametersLoading++;controls();
   try{const text=await f.text();if(seq===generation&&!busy){values.set(id,text);el(id+'_name').textContent=f.name;el(id+'_recent').value='';el('off_error').textContent='';}}
   catch(e){el('off_error').textContent=e.message;}finally{parametersLoading--;controls();}
  }
  input.onchange=()=>{if(input.files.length)accept(input.files);};
  zone.onclick=()=>{if(!busy&&!appBusy)input.click();};
  zone.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();zone.click();}};
  zone.ondragover=e=>{e.preventDefault();if(!busy&&!appBusy)zone.classList.add('drag-over');};
  zone.ondragleave=()=>zone.classList.remove('drag-over');
  zone.ondrop=e=>{e.preventDefault();e.stopPropagation();zone.classList.remove('drag-over');accept(e.dataTransfer.files);};
  el(id+'_recent').onchange=async()=>{
   const key=el(id+'_recent').value;if(!key)return;
   const seq=++generation;parametersLoading++;controls();
   try{const p=await request('/offline/parameter/'+encodeURIComponent(key));if(seq===generation&&!busy){values.set(id,p.text);el(id+'_name').textContent=p.path;input.value='';el('off_error').textContent='';}}
   catch(e){el('off_error').textContent=e.message;}finally{parametersLoading--;controls();}
  };
 }
 async function refresh(){
  if(refreshing||busy)return;refreshing=true;
  try{
   catalog=await request('/offline/catalog');if(!catalog.ready){el('off_source').textContent='等待 Docker 数据目录就绪；未连接头环时仍可处理已有数据。';return;}
   const select=el('off_dataset'),old=select.value;select.replaceChildren(new Option(egoI18n.t('请选择已有联合录制或已准备的 BAG'),''));
   for(const p of catalog.datasets.filter(p=>!p.mode||p.mode==='camera_imu'))select.append(new Option((p.kind==='raw'?egoI18n.t('原始录制：'):egoI18n.t('已准备 BAG：'))+p.path,p.id));
   if(catalog.datasets.some(p=>p.id===old))select.value=old;
   for(const id of ['off_camera','off_candidate','off_imu']){
    const s=el(id+'_recent'),previous=s.value;s.replaceChildren(new Option(egoI18n.t('从本机已有参数中选择，或拖入文件'),''));
    for(const p of catalog.parameters){const accepted=id==='off_imu'?p.kind==='imu':id==='off_candidate'?p.kind==='candidate':p.kind==='camera'||p.kind==='candidate';if(accepted)s.append(new Option(p.path,p.id));}
    if(Array.from(s.options).some(o=>o.value===previous))s.value=previous;
   }
   showSource();
  }catch(e){el('off_error').textContent=e.message;}finally{refreshing=false;controls();}
 }
 function showSource(){const p=catalog?.datasets.find(p=>p.id===el('off_dataset').value);el('off_source').textContent=p?egoI18n.t('数据目录：')+p.path:egoI18n.t('本机数据根目录：')+(catalog?.root||egoI18n.t('尚未就绪'));controls();}
 el('off_refresh').onclick=refresh;el('off_dataset').onchange=showSource;
 el('off_action').onchange=controls;el('off_ack').onchange=controls;
 el('off_start').onclick=async()=>{
  if(el('off_start').disabled)return;
  const body={dataset:el('off_dataset').value,action:el('off_action').value,experimental_ack:el('off_ack').checked,imu_yaml:values.get('off_imu')||''};
  if(body.action==='validate')body.candidate_yaml=values.get('off_candidate')||'';else body.camera_yaml=values.get('off_camera')||'';
  busy=true;window.egoOfflineBusy=true;controls();el('off_error').textContent='';
  try{await request('/offline/start',body);}catch(e){busy=false;window.egoOfflineBusy=false;el('off_error').textContent=e.message;}finally{await poll();controls();}
 };
 el('off_stop').onclick=async()=>{try{await request('/offline/stop',{});}catch(e){el('off_error').textContent=e.message;}};
 el('off_open').onclick=async()=>{try{await request('/offline/open',{});}catch(e){el('off_error').textContent=e.message;}};
 let polling=false,lastRunning=false;
 async function poll(){
  if(polling)return;polling=true;
  try{
   const [state,app]=await Promise.all([request('/offline/state'),request('/state')]);
   busy=state.busy;window.egoOfflineBusy=busy;window.egoOfflineView=state;appBusy=!['READY','FAILED','DONE'].includes(app.stage);
   el('off_status').textContent=state.message;el('off_progress').hidden=!busy;
   el('off_results').hidden=state.stage==='IDLE';el('off_output').textContent=state.output&&!busy?egoI18n.t('结果保存目录：')+state.output:'';el('off_open').disabled=!state.output||busy;
   if(busy&&!lastRunning)el('off_log_panel').open=true;lastRunning=busy;const nearEnd=el('off_logs').scrollHeight-el('off_logs').scrollTop-el('off_logs').clientHeight<60;el('off_logs').textContent=state.logs.join('\n');if(nearEnd)el('off_logs').scrollTop=el('off_logs').scrollHeight;el('off_files').replaceChildren();
   for(const name of state.files){const a=document.createElement('a');a.className='link';a.href='/offline/files/'+encodeURIComponent(name);a.textContent=name;a.target='_blank';a.rel='noopener';el('off_files').append(a);}
   el('off_metrics').replaceChildren();
   if(state.result?.residuals){
    const table=document.createElement('table');table.style.width='100%';table.style.textAlign='left';
    const heading=document.createElement('tr');for(const label of [egoI18n.t('误差项'),egoI18n.t('平均值'),'RMS','P95']){const th=document.createElement('th');th.textContent=label;heading.append(th);}table.append(heading);
    const labels={cam0_px:egoI18n.t('左相机（px）'),cam1_px:egoI18n.t('右相机（px）'),gyro_rad_s:egoI18n.t('陀螺仪（rad/s）'),accel_m_s2:egoI18n.t('加速度计（m/s²）')};
    for(const [key,r] of Object.entries(state.result.residuals)){const tr=document.createElement('tr');for(const v of [labels[key]||key,...['mean','rms','p95'].map(k=>Number(r[k]).toPrecision(5))]){const td=document.createElement('td');td.textContent=v;tr.append(td);}table.append(tr);}el('off_metrics').append(table);
   }
   if(!catalog?.ready)refresh();controls();
  }catch(e){el('off_status').textContent=egoI18n.t('本地工具连接中断，请检查启动终端。');}finally{polling=false;}
 }
 controls();refresh();poll();setInterval(poll,1200);
})();
