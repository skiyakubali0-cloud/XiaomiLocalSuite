'use strict';
const $=id=>document.getElementById(id);
let busy=false, selected=null, rows=[];
function command(action){
 if(!/^(status|(screen|control):(on|off|list|[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+:(on|off)))$/.test(action))throw new Error('无效操作');
 if(!window.ksu||typeof window.ksu.exec!=='function')return Promise.reject(new Error('请从 KernelSU 的小爱模块打开。'));
 return new Promise((resolve,reject)=>{
  const key='aiprivacy_'+Date.now()+'_'+Math.floor(Math.random()*100000);
  const timer=setTimeout(()=>{delete window[key];reject(new Error('读取超时，请刷新后再试。'));},20000);
  window[key]=(code,out,err)=>{clearTimeout(timer);delete window[key];if(Number(code)!==0){reject(new Error(err||out||'操作失败'));return;}
   try{resolve(JSON.parse(out));}catch(e){reject(new Error('状态响应无效，未确认操作成功。'));}};
  try{window.ksu.exec('/system/bin/sh /data/adb/modules/xuanyuan-os4-xiaoai/privacy.sh '+action,'{}',key);}
  catch(e){clearTimeout(timer);delete window[key];reject(e);}
 });
}
function apply(state){
 if(state.ready!==true)throw new Error('后台未就绪');
 for(const type of ['screen','control']){
  if(typeof state[type]!=='boolean')throw new Error('缺少系统开关状态');
  $(type).checked=state[type];$(type).disabled=false;$(type+'-manage').disabled=!state[type];
 }
}
async function work(fn){
 if(busy)return;busy=true;$('message').textContent='正在读取系统…';
 document.querySelectorAll('button,input').forEach(e=>e.disabled=true);
 try{await fn();$('message').textContent='已与系统权限服务核对。';}
 catch(e){$('message').textContent=e.message;}
 finally{busy=false;$('refresh').disabled=false;$('open').disabled=false;$('back').disabled=false;$('search').disabled=false;}
}
function render(){
 $('apps').replaceChildren();const query=$('search').value.toLowerCase();
 for(const row of rows.filter(r=>(r.label+' '+r.package).toLowerCase().includes(query))){
  const card=document.createElement('div');card.className='card row';
  const label=document.createElement('label');label.textContent=row.label;
  const pkg=document.createElement('div');pkg.className='pkg';pkg.textContent=row.package;label.appendChild(pkg);
  const toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=row.allowed;toggle.disabled=row.blocked;
  toggle.setAttribute('aria-label',row.label);if(row.blocked)label.appendChild(document.createTextNode(' · 系统策略限制'));
  toggle.addEventListener('change',()=>work(async()=>{
   const enable=toggle.checked;await command(selected+':'+row.package+':'+(enable?'on':'off'));
   rows=(await command(selected+':list')).apps;render();
  }));card.append(label,toggle);$('apps').appendChild(card);
 }
 if(!$('apps').children.length)$('apps').textContent='没有符合条件的可管理应用。';
}
async function refresh(){
 await work(async()=>{const state=await command('status');apply(state);
  if(selected){if(!state[selected]){selected=null;$('app-page').hidden=true;$('detail').hidden=false;}
   else{rows=(await command(selected+':list')).apps;render();}}
 });
}
$('open').onclick=()=>{$('overview').hidden=true;$('detail').hidden=false;refresh();};
for(const type of ['screen','control']){
 $(type).onchange=()=>{const enable=$(type).checked;work(async()=>apply(await command(type+':'+(enable?'on':'off'))));};
 $(type+'-manage').onclick=()=>work(async()=>{
  rows=(await command(type+':list')).apps;selected=type;$('search').value='';
  $('detail').hidden=true;$('app-page').hidden=false;$('app-title').textContent=type==='screen'?'AI识屏管理':'AI智控管理';render();
 });
}
$('back').onclick=()=>{selected=null;$('app-page').hidden=true;$('detail').hidden=false;refresh();};
$('search').oninput=render;$('refresh').onclick=refresh;
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});refresh();
