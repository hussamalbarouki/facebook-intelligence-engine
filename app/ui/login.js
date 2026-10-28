import RFB from '/browser-assets/core/rfb.js';

const $=id=>document.getElementById(id);
let rfb=null, heartbeat=null;
const msg=(message,bad=false)=>{
 $('message').textContent=message;
 $('message').className=bad?'error':'';
};
async function api(path,opts={}){
 const res=await fetch(path,{credentials:'same-origin',cache:'no-store',...opts});
 const data=await res.json().catch(()=>({}));
 if(!res.ok)throw Error(data.detail || 'تعذّر الاتصال بالخادم ('+res.status+')');
 return data;
}
function connect(){
 $('auth').hidden=true;
 $('browser').hidden=false;
 $('screen').replaceChildren();
 $('state').textContent='جاري الاتصال بشاشة Chromium…';
 const proto=location.protocol==='https:'?'wss:':'ws:';
 rfb=new RFB($('screen'),proto+'//'+location.host+'/v1/browser-session/stream');
 rfb.scaleViewport=true;
 rfb.resizeSession=false;
 rfb.showDotCursor=true;
 rfb.addEventListener('connect',()=>{$('state').textContent='المتصفح متصل — سجّل دخول Facebook';msg('');});
 rfb.addEventListener('disconnect',e=>{
  $('state').textContent='انقطع اتصال الشاشة';
  if(!e.detail.clean)msg('انقطع المتصفح أو انتهت جلسة الإدارة. أعد فتح الصفحة للتأكد.',true);
 });
 if(heartbeat)clearInterval(heartbeat);
 heartbeat=setInterval(async()=>{
  try{await api('/v1/browser-session/status');}
  catch(e){msg('جلسة الإدارة انتهت. احفظ وأعد المحاولة إذا لزم.',true);clearInterval(heartbeat);}
 },25000);
}
$('start').addEventListener('click',async()=>{
 const key=$('admin-key').value.trim();
 if(!key){msg('أدخل مفتاح إدارة المحرك.',true);return;}
 $('start').disabled=true;
 try{
  await api('/v1/browser-session/start',{
   method:'POST',headers:{'X-API-Key':key}
  });
  $('admin-key').value='';
  connect();
 }catch(e){msg(e.message,true);}
 finally{$('start').disabled=false;}
});
$('save').addEventListener('click',async()=>{
 $('save').disabled=true;
 try{
  const out=await api('/v1/browser-session/save',{method:'POST'});
  try{rfb?.disconnect();}catch(_){}
  if(heartbeat)clearInterval(heartbeat);
  $('browser').hidden=true;
  $('auth').hidden=false;
  msg(out.saved?'تم حفظ ملف متصفح Facebook على الخادم وإغلاقه. تستطيع الآن تشغيل استخراج المنشورات.':'أُغلق المتصفح لكن لم نجد جلسة Facebook مسجّلة. سجّل الدخول أولًا ثم احفظ.',!out.saved);
 }catch(e){msg(e.message,true);}
 finally{$('save').disabled=false;}
});
$('focus').addEventListener('click',()=>{rfb?.focus();$('screen').focus();});
window.addEventListener('DOMContentLoaded',async()=>{
 try{
   const out=await api('/v1/browser-session/status');
   if(out.controller_authorized&&out.login_active)connect();
 }catch(_){/* Not authenticated yet; show the password field. */}
});