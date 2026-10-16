'use strict';
const features = [
 ['suggestions','☆','小爱建议','管理出行、日程和生活提醒，设置及权限以原厂页面为准。','打开小爱建议'],
 ['screen','◎','屏幕问答 / 识屏','选择手势、圈选等识屏方式。','设置识屏'],
 ['control','⌘','帮操作手机','按应用选择小爱可控制的范围。','管理应用'],
 ['memory','◇','小爱记忆','选择记忆及收藏方式，管理已有记忆。','管理记忆'],
 ['wakeup','◉','语音唤醒','设置语音、按键唤醒并录入声纹。','设置唤醒'],
 ['translate','文','翻译','管理 AI 字幕、对话翻译及权限。','设置翻译'],
 ['write','✎','写作','在小爱对话中提出写作、改写或总结需求。','打开小爱'],
 ['aicall','☎','AI 通话','选择接听方式、开场白与通话辅助。','设置 AI 通话'],
 ['callerid','＃','陌生号码识别','管理号码识别、联网查询及号码库。','设置号码识别']
];
const notice=document.getElementById('notice');
const root=document.getElementById('features');
for(const [id,icon,title,description,label] of features){
 const article=document.createElement('article');article.className='card';
 for(const [tag,cls,value] of [['div','icon',icon],['h2','',title],['p','',description],['div','state','正在检查入口…']]){
  const element=document.createElement(tag);element.className=cls;element.textContent=value;
  if(cls==='state')element.id='state-'+id;article.appendChild(element);
 }
 const button=document.createElement('button');button.textContent=label;button.dataset.action=id;button.disabled=true;
 button.addEventListener('click',()=>launch(id,button));article.appendChild(button);root.appendChild(article);
}
function command(action){
 if(action!=='status'&&!features.some(f=>f[0]===action))return Promise.reject(new Error('未知功能'));
 if(!window.ksu||typeof window.ksu.exec!=='function')return Promise.reject(new Error('请从 KernelSU Next → 超级小爱模块 → 功能页面打开。'));
 return new Promise((resolve,reject)=>{
  const callback='xiaoai_'+Date.now()+'_'+Math.floor(Math.random()*100000);
  const timer=setTimeout(()=>{delete window[callback];reject(new Error('操作超时，请检查手机页面后再试。'));},15000);
  window[callback]=(code,out,err)=>{clearTimeout(timer);delete window[callback];Number(code)===0?resolve(out||''):reject(new Error(err||out||'操作失败'));};
  try{window.ksu.exec('/system/bin/sh /data/adb/modules/xuanyuan-os4-xiaoai/control.sh '+action,'{}',callback);}
  catch(error){clearTimeout(timer);delete window[callback];reject(error);}
 });
}
let refreshing=false;
async function refresh(){
 if(refreshing)return;refreshing=true;
 try{
  const output=await command('status');const state=Object.fromEntries(output.trim().split(/\r?\n/).map(line=>line.split('|')));
  for(const [id] of features){
   const ready=state[id]==='ready';const text=document.getElementById('state-'+id);
   text.textContent=ready?'入口已就绪':'入口不可用';text.classList.toggle('warn',!ready);
   document.querySelector('button[data-action="'+id+'"]').disabled=!ready;
  }
  const lookup={on:'联网识别开关已开启',off:'联网识别开关已关闭',unknown:'联网识别尚未配置'};
  if(state.callerid==='ready')document.getElementById('state-callerid').textContent=lookup[state.callerid_switch]||'入口已就绪';
  notice.textContent='请选择需要使用的功能。';
 }catch(error){notice.textContent=error.message;for(const [id] of features)document.getElementById('state-'+id).textContent='尚未读取设备状态';}
 finally{refreshing=false;}
}
async function launch(id,button){
 button.disabled=true;
 try{const output=await command(id);if(/Error:|Exception|does not exist/.test(output))throw new Error(output);notice.textContent='已打开功能页面，设置完成后返回即可。';}
 catch(error){notice.textContent=error.message;}
 finally{button.disabled=false;}
}
document.getElementById('refresh').addEventListener('click',refresh);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
refresh();
