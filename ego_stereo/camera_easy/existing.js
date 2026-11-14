/* One input dataset per module; parameter files are needed only for the joint step. */
(() => {
 const el=id=>document.getElementById(id);let generation=0,catalog=null;
 const mode=el('mode'),workflow=el('workflow'),select=el('existing_dataset');
 function showSource(){
  const item=catalog?.datasets.find(p=>p.id===select.value);
  el('existing_source').textContent=item?'已选择：'+item.path:'';
 }
 async function refresh(){
  const seq=++generation,kind=mode.value;
  if(workflow.value!=='existing')return;
  try{
   const response=await fetch('/offline/catalog'),data=await response.json();
   if(!response.ok)throw Error(data.error||'无法读取录制列表');
   if(seq!==generation||mode.value!==kind||workflow.value!=='existing')return;
   catalog=data;const old=select.value;
   const items=data.datasets.filter(p=>(p.mode||'camera_imu')===kind);
   select.replaceChildren(new Option(items.length?'请选择已录制的数据':'未找到本工具的录制，请先录制或检查数据目录',''));
   for(const p of items)select.append(new Option(p.path,p.id));
   if(items.some(p=>p.id===old))select.value=old;
   showSource();
  }catch(e){el('existing_source').textContent=e.message;}
 }
 function change(){
  el('existing_options').hidden=workflow.value!=='existing';
  el('existing_hint').textContent=mode.value==='camera'?'选择相机录制即可计算，不需要 IMU 文件。自动读取原录制的标定板尺寸；原配置缺失时使用下方实测尺寸。':mode.value==='imu'?'选择静止 IMU 录制即可分析，不需要 Camera 文件或标定板。当前读取本工具保存的 imu_samples.csv 和 imu_capture.json。':'选择联合运动录制，并在下方拖入第一步 Camera YAML 与第二步 IMU 噪声 YAML。无需拖 PDF 或 TXT。';
  refresh();
 }
 const modeChange=mode.onchange;mode.onchange=()=>{if(modeChange)modeChange();select.value='';change();};
 const workflowChange=workflow.onchange;workflow.onchange=()=>{if(workflowChange)workflowChange();change();};
 select.onchange=showSource;el('existing_refresh').onclick=refresh;change();
})();
