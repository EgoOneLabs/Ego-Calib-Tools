/* Main flow reuses only explicitly remembered parameters for the same device. */
(() => {
 let generation=0;
 const mode=document.getElementById('mode'),device=document.getElementById('device_id');
 async function loadDefaults(){
  if(mode.value!=='camera_imu')return;
  const ident=device.value,seq=++generation;
  try{
   const response=await fetch('/joint/parameters/'+encodeURIComponent(ident));
   const data=await response.json();if(!response.ok)throw Error(data.error||'无法读取已保存参数');
   if(seq!==generation||device.value!==ident||mode.value!=='camera_imu'||window.egoOfflineBusy)return;
   for(const [kind,id] of [['camera','joint_camera_file'],['imu','joint_imu_file']]){
    const item=data[kind];if(!item||selectedYaml.has(id)||document.getElementById(id).disabled)continue;
    const file={name:item.name,size:new TextEncoder().encode(item.text).length,text:async()=>item.text};
    selectedYaml.set(id,file);
    const status=document.getElementById(id+'_status');status.textContent='已带入：'+item.name+'（设备 '+ident+'，请核对）';status.title=item.path;
    document.getElementById(id+'_clear').disabled=false;
   }
  }catch(e){document.getElementById('parameter_note').textContent=e.message+'；也可以手动拖入两个参数文件。';}
 }
 const changeMode=mode.onchange;
 mode.onchange=()=>{if(changeMode)changeMode();loadDefaults();};
 device.addEventListener('change',()=>{
  generation++;
  for(const id of ['joint_camera_file','joint_imu_file']){
   selectedYaml.delete(id);document.getElementById(id).value='';document.getElementById(id+'_status').textContent='设备已改变，请重新确认参数';
  }
  loadDefaults();
 });
 document.getElementById('main_open').onclick=()=>post('/open-output');
 loadDefaults();
})();
