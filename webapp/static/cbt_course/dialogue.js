"use strict";
const root = document.querySelector(".dialogue-page");
const byId = id => document.getElementById(id);
let current = JSON.parse(byId("dialogue-initial").textContent);
let busy = false;
let retry = null;
let retryMode = "retry";
let hold = false;
let saveState = current ? current.turn_status : "ready";
let operation = "send";
let streamDraft = null;
let outgoing = null;
let draftRevision = 0;
let composing = false;
const notices = {
  refresh:"记录已更新，请刷新后继续；原输入会保留。",
  processing:"上一轮仍在处理中，请稍后刷新查看。",
  read_only:"这份历史记录仅供查看，请从课程入口继续。",
  edit:"这次输入暂时无法提交，请检查内容后重新发送。",
  turn_failed:"这轮暂时没能完成，请保留原输入，稍后重试。",
  result_unknown:"暂时没能取得本轮结果，请先刷新记录确认。",
  saved:"本轮已经保存，页面暂未更新，请刷新查看。",
  load_failed:"记录暂时无法读取，请稍后刷新重试。",
  sign_in:"请先使用邀请码登录，再继续查看。",
  forbidden:"请刷新页面，并确认已完成数据记录告知。",
  not_found:"暂时找不到这份记录，请返回课程入口查看。",
  too_long:"这条消息较长，请缩短后再发送。",
  slow_down:"操作有些频繁，请稍后再试。"
};
class PublicNotice extends Error {
  constructor(notice, recovery="check") {
    super(Object.hasOwn(notices,notice) ? notices[notice] : notices.result_unknown);
    this.recovery=recovery;
  }
}
const safeMessage = e => e instanceof PublicNotice ? e.message : notices.result_unknown;
const labels = {situation:"事情",thought:"想法",emotion:"心情",behavior:"做法",thought_belief:"对想法的相信程度",emotion_intensity:"情绪强度"};
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function error(text){byId("dialogue-error").textContent=text;byId("dialogue-error").hidden=!text;}
function requestHeaders(body){
  const headers={};
  if(body!==undefined){headers["Content-Type"]="application/json";headers["X-CSRF-Token"]=decodeURIComponent((document.cookie.split("; ").find(x=>x.startsWith("csrf_token="))||"=").split("=")[1]||"");}
  return headers;
}
async function api(url,body){
  let response,data;
  try {
    const headers=requestHeaders(body);
    response=await fetch(url,{method:body===undefined?"GET":"POST",credentials:"same-origin",headers,body:body===undefined?undefined:JSON.stringify(body)});
    data=await response.json();
  } catch (_) { throw new PublicNotice("result_unknown"); }
  // Only known public notices may reach the page, never raw response/exception text.
  if(!response.ok)throw new PublicNotice(data && data.notice,data && data.recovery);
  if(!data || typeof data!=="object")throw new PublicNotice("result_unknown");
  return data;
}
function showStreamDraft(text){
  const list=byId("dialogue-messages");
  if(!streamDraft){streamDraft=node("article","","dialogue-message agent provisional");list.append(streamDraft);}
  streamDraft.textContent+=text;list.scrollTop=list.scrollHeight;
  byId("dialogue-save").textContent="正在生成回复，尚未确认保存……";
}
function beginOutgoing(body,submittedDraft){
  if(body.action!=="chat")return;
  const input=byId("dialogue-input");
  const continuing=outgoing?.body.idempotency_key===body.idempotency_key;
  if(!continuing)outgoing={body,status:"pending",clearRevision:null,restoredRevision:null};
  const ownsDraft=submittedDraft || outgoing.restoredRevision===draftRevision;
  if(ownsDraft && input.value.trim()===body.content){
    input.value="";draftRevision+=1;
    outgoing.clearRevision=draftRevision;outgoing.restoredRevision=null;
  }
  outgoing.status="pending";
}
function restoreDraft(body){
  if(outgoing?.body.idempotency_key!==body.idempotency_key)return;
  const input=byId("dialogue-input");
  if(outgoing.clearRevision===draftRevision && input.value===""){
    input.value=body.content;draftRevision+=1;outgoing.restoredRevision=draftRevision;
  }
}
async function streamApi(url,body){
  let response;
  try{response=await fetch(url,{method:"POST",credentials:"same-origin",headers:requestHeaders(body),body:JSON.stringify(body)});}
  catch(_){throw new PublicNotice("result_unknown");}
  if(!response.ok){
    let data;try{data=await response.json();}catch(_){throw new PublicNotice("result_unknown");}
    throw new PublicNotice(data&&data.notice,data&&data.recovery);
  }
  if(!response.headers.get("content-type")?.includes("text/event-stream") || !response.body?.getReader)throw new PublicNotice("result_unknown");
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer="",result=null;
  function consume(frame){
    const raw=frame.split(/\r?\n/).filter(line=>line.startsWith("data:")).map(line=>line.slice(5).trimStart()).join("\n");
    if(!raw)return;
    let event;try{event=JSON.parse(raw);}catch(_){throw new PublicNotice("result_unknown");}
    if(event.type==="error")throw new PublicNotice(event.notice,event.recovery);
    if(event.type==="reply_delta"){
      if(result || typeof event.text!=="string")throw new PublicNotice("result_unknown");
      showStreamDraft(event.text);
    }else if(event.type==="result"){
      if(result || !event.data?.conversation?.course)throw new PublicNotice("result_unknown");
      result=event.data;
    }else if(!["start","heartbeat"].includes(event.type))throw new PublicNotice("result_unknown");
  }
  try{
    while(true){
      const chunk=await reader.read();buffer+=decoder.decode(chunk.value||new Uint8Array(),{stream:!chunk.done});
      let split;
      while((split=buffer.indexOf("\n\n"))>=0){consume(buffer.slice(0,split));buffer=buffer.slice(split+2);}
      if(chunk.done)break;
    }
    if(buffer.trim() || !result)throw new PublicNotice("result_unknown");
    return result;
  }catch(e){
    try{await reader.cancel();}catch(_){/* A lost connection is reconciled by the original request key. */}
    throw e;
  }finally{reader.releaseLock();}
}
function render(){if(!current)return;const c=current.course;
  byId("dialogue-phase").textContent=c.phase_label;byId("dialogue-mode").textContent=current.read_only&&current.status!=="completed"?"历史记录（只读）":current.status==="completed"?"已完成":current.status==="ended"?"本次已结束":{teaching:"一起学习",communicating:"先聊一聊",paused:"已暂停"}[c.flow_mode];
  const m=c.details;const material=[m.material||"",m.check?m.check.story+"\n\n"+m.check.prompt:"",m.check&&m.check.hint?"提示："+m.check.hint:""].filter(Boolean).join("\n\n");byId("dialogue-material").textContent=material;
  streamDraft=null;
  const messages=current.messages.map(x=>node("article",x.content,"dialogue-message "+x.role));
  if(outgoing){
    const bubble=node("article",outgoing.body.content,"dialogue-message learner pending");
    bubble.append(node("small",{pending:"发送中……",unknown:"保存结果待核对",failed:"本轮未完成，原消息已保留"}[outgoing.status],"dialogue-pending-status"));
    messages.push(bubble);
  }
  byId("dialogue-messages").replaceChildren(...messages);byId("dialogue-messages").scrollTop=byId("dialogue-messages").scrollHeight;
  byId("dialogue-case").textContent=c.case_kind==="fictional"?"课程例子练习（不是本人经历）":"本人愿意讨论的例子";
  const items=[];for(const [field,label] of Object.entries(labels)){items.push(node("dt",label));const value=c.records[field]||c.ratings[field];items.push(node("dd",value?(String(value.value)+(field in c.ratings?" / 10":"")):(c.fields[field].status==="not_applicable"?"课程例子不要求本人评分":c.fields[field].deferred?"本项暂留":"尚未记录")));}byId("dialogue-records").replaceChildren(...items);
  byId("dialogue-confirmation").textContent=c.confirmation?"这份记录已由本人核对。":"记录仍待本人核对。";
  const goal=[];if(m.goal)goal.push(node("h3","希望练习的方向"),node("p",m.goal.value),node("p",m.goal_skipped?"暂不设置（草稿未确认）":m.goal_confirmed_revision===m.goal.revision?"本人已确认":"草稿待核对"));if(m.plan_status!=="undecided")goal.push(node("p",m.plan_status==="accepted"?"愿意课后尝试（尚未记录实际执行）":"暂不安排课后练习"));byId("dialogue-goal").replaceChildren(...goal);
  const results=[];if(m.attempts)for(const key of ["first","retry"]){const a=m.attempts[key];if(a.status==="not_started")continue;results.push(node("h3",key==="first"?"首次练习":"补练（单独保留）"));for(const row of a.answers)results.push(node("p",`第${row.question_index+1}题：${row.sources.map(x=>x.quote).join("；")}\n${row.reason}`));}byId("dialogue-results").replaceChildren(...results);
  byId("dialogue-input").disabled=current.read_only||current.status!=="active";
  byId("dialogue-send").disabled=busy||hold||current.read_only||current.status!=="active";
  const resume=byId("dialogue-session-resume");
  if(resume){
    resume.hidden=current.status!=="ended"||current.read_only||!c.controls.some(x=>x.id==="resume_session");
    resume.disabled=busy||hold;
  }
  byId("dialogue-save").textContent=busy?(operation==="check"?"正在核对保存结果……":"正在发送，等待回应……"):
    ({saved:"最近一轮已保存，可刷新查看",failed:"上一轮未完成，输入已保留",interrupted:"上一轮未完成，可重试原输入",pending:"上一轮仍在处理，请刷新查看",unknown:"本轮结果待确认，请刷新查看",ready:"记录已加载"}[saveState]||"记录已加载");
  byId("dialogue-retry").hidden=!retry;byId("dialogue-retry").disabled=busy;
  byId("dialogue-retry").textContent=retryMode==="check"?"查看上一轮结果":"重试上一轮原输入";
}
function finish(body){
  retry=null;hold=false;saveState="saved";error("");
  if(outgoing?.body.idempotency_key===body.idempotency_key){
    if(outgoing.restoredRevision===draftRevision && byId("dialogue-input").value.trim()===body.content){
      byId("dialogue-input").value="";draftRevision+=1;
    }
    outgoing=null;
  }
}
async function reconcile(body){
  const view=await api(`/api/cbt-dialogue/${current.id}?request_key=${encodeURIComponent(body.idempotency_key)}`);
  if(!view.course || !Array.isArray(view.messages))throw new PublicNotice("result_unknown");
  current=view;
  if(view.request_status==="saved"){finish(body);return;}
  if(view.revision!==body.expected_revision || (view.request_status!=="pending" && !view.request_retryable)){
    restoreDraft(body);outgoing=null;
    retry=null;hold=false;saveState=view.turn_status;error(notices.refresh);return;
  }
  retry=body;
  retryMode=view.request_status==="pending"?"check":"retry";
  hold=view.request_status==="pending" || view.request_status==="missing";
  saveState=view.request_status==="missing"?"unknown":view.request_status;
  if(outgoing)outgoing.status=view.request_status==="pending"?"pending":view.request_status==="missing"?"unknown":"failed";
  if(view.request_status==="pending")error(notices.processing);
}
async function send(content,action="chat",saved=null){
  if(busy || (hold && !saved))return;
  const same=retry && retry.content===content && retry.action===action;
  const body=saved || (same?retry:{content,action,idempotency_key:crypto.randomUUID(),expected_revision:current.revision});
  beginOutgoing(body,!saved);
  busy=true;operation="send";error("");render();
  try{
    const result=body.action==="chat"?await streamApi(`/api/cbt-dialogue/${current.id}/messages/stream`,body):await api(`/api/cbt-dialogue/${current.id}/messages`,body);
    if(!result.conversation || !result.conversation.course)throw new PublicNotice("result_unknown");
    current=result.conversation;finish(body);
  }catch(e){
    if(outgoing)outgoing.status="unknown";
    retry=body;retryMode="check";hold=true;saveState="unknown";error(safeMessage(e));
    try{
      await reconcile(body);
      if(e instanceof PublicNotice && ["refresh","edit","stop"].includes(e.recovery) && retry){
        retry=null;hold=false;if(e.recovery==="edit"){saveState="failed";if(outgoing)outgoing.status="failed";}
      }
    }catch(_){/* Outcome stays unknown. Check before allowing another request. */}
  }finally{if(outgoing && outgoing.status!=="pending")restoreDraft(body);busy=false;render();}
}
async function refresh(){
  if(busy)return;busy=true;operation="check";render();
  try{
    if(retry)await reconcile(retry);
    else{const view=await api(`/api/cbt-dialogue/${current.id}`);if(!view.course)throw new PublicNotice("load_failed");current=view;saveState=view.turn_status;error("");}
  }catch(e){error(safeMessage(e));}finally{if(retry && outgoing && outgoing.status!=="pending")restoreDraft(retry);busy=false;render();}
}
if(byId("dialogue-start"))byId("dialogue-start").addEventListener("click",async()=>{try{const result=await api("/api/cbt-dialogue/start",{});if(typeof result.url!=="string" || !result.url.startsWith("/cbt-course/dialogue/"))throw new PublicNotice("load_failed");location.href=result.url;}catch(e){error(safeMessage(e));}});
if(current && byId("dialogue-session-resume"))byId("dialogue-session-resume").addEventListener("click",()=>send("","resume_session"));
if(current){
  byId("dialogue-input").addEventListener("input",()=>{draftRevision+=1;});
  byId("dialogue-input").addEventListener("compositionstart",()=>{composing=true;});
  byId("dialogue-input").addEventListener("compositionend",()=>{composing=false;});
  byId("dialogue-form").addEventListener("submit",e=>{e.preventDefault();if(composing||e.isComposing)return;const text=byId("dialogue-input").value.trim();if(text)return send(text);});
  byId("dialogue-retry").addEventListener("click",()=>{if(retry){if(retryMode==="check")refresh();else send(retry.content,retry.action,retry);}});
  byId("dialogue-refresh").addEventListener("click",refresh);render();
}else{byId("dialogue-refresh").hidden=true;}
