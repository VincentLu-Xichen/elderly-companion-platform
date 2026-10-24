/* Exercise the real submit function with a delayed transport, without a browser. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../webapp/static/cbt_course/course.js'), 'utf8');
const submit = source.slice(source.indexOf('  async function submit('), source.indexOf('  function pollReflection('));
function env() {
  const ctx = vm.createContext({crypto: require('node:crypto')});
  vm.runInContext(`
    var busy=false, retry=null, course={revision:1,current_step:'learning_goal'}, endpoint='/test';
    var input={value:'原消息',disabled:false,focus(){}},count={textContent:'3 / 2000'};
    var requests=[],bubbles=[],elements={};
    function courseElement(){return {type:'',remove(){},addEventListener(){}}}
    function appendCourseMessage(role,text){
      var bubble={textContent:text}; bubbles.push({role,bubble});
      return {className:'',querySelector(){return bubble},append(){}};
    }
    function render(next){course=next}
    function courseCookie(){return 'test'}
    var window={matchMedia(){return {matches:true}}};
    async function courseRevealReply(text,paint){paint(text)}
    var document={getElementById(id){return elements[id] || (elements[id]={textContent:'',scrollTop:0,scrollHeight:10})}};
    function courseStreamRequest(url,payload){requests.push(payload);return new Promise((resolve,reject)=>{resolveRequest=resolve;rejectRequest=reject})}
    var resolveRequest,rejectRequest;
    function pollReflection(){}
  ` + submit, ctx);
  return ctx;
}
(async()=>{
  const a=env();
  let pending=a.submit();
  assert.equal(a.input.value,''); // Before any server reply.
  assert.equal(a.count.textContent,'0 / 2000');
  assert.equal(a.requests[0].content,'原消息');
  a.rejectRequest(new Error('synthetic transport failure'));
  await pending;
  assert.equal(a.retry.payload.content,'原消息');
  const key=a.retry.payload.idempotency_key;
  a.input.value='后来输入的新草稿';
  pending=a.submit('chat',a.retry);
  assert.equal(a.requests[1].idempotency_key,key);
  assert.equal(a.requests[1].content,'原消息');
  a.resolveRequest({reply:'已保存',course:a.course});await pending;
  assert.equal(a.input.value,'后来输入的新草稿');
  const b=env();
  pending=b.submit('skip_learning_goal');
  assert.equal(b.input.value,'原消息');
  b.resolveRequest({reply:'继续',course:b.course});await pending;
  assert.equal(b.input.value,'原消息');
  assert.equal(b.requests[0].content,'');
  const c=env();
  c.course.lesson2={actions:[{action:'continue_lesson2',label:'继续雨天情境'}]};
  pending=c.submit('continue_lesson2');
  assert.equal(c.bubbles[0].bubble.textContent,'继续雨天情境');
  c.resolveRequest({reply:'进入雨天',course:c.course});await pending;
  console.log('Draft lifecycle passed: immediate clear, retry snapshot/key, newer draft, control draft.');
})().catch(error=>{console.error(error);process.exitCode=1});
