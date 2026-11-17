function csrf(){return document.cookie.split('; ').find(x=>x.startsWith('csrf_token='))?.slice(11)||'';}
async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf())},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'请核对输入后重试。');return data;}
function show(error){document.querySelector('#entry-error').textContent=error.message||'暂时无法完成，请稍后重试。';}
document.querySelector('#login-form')?.addEventListener('submit',async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{await post('/api/session/invite',{code:document.querySelector('#invite-code').value.trim()});location.href='/app';}catch(error){show(error);button.disabled=false;}});
document.querySelector('#agree')?.addEventListener('change',e=>{document.querySelector('#consent').disabled=!e.target.checked;});
document.querySelector('#consent')?.addEventListener('click',async e=>{e.target.disabled=true;try{await post('/api/consents',{agreed:true});location.href='/cbt-course/dialogue';}catch(error){show(error);e.target.disabled=false;}});
document.querySelector('#logout')?.addEventListener('click',async()=>{try{await post('/api/session/logout',{});location.href='/';}catch(error){show(error);}});
