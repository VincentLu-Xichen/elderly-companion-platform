const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ctx=vm.createContext({});
vm.runInContext(`var frames=[], listeners={}, document={hidden:false,addEventListener(k,f){listeners[k]=f},removeEventListener(k){delete listeners[k]}};
function requestAnimationFrame(f){frames.push(f);return frames.length}
function cancelAnimationFrame(){};`,ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../webapp/static/cbt_course/stream.js'),'utf8'),ctx);
(async()=>{
  const parts=[];
  const done=ctx.courseRevealReply('先停下追问😀，围绕原事件回顾。',p=>parts.push(p));
  let time=0;
  while(ctx.frames.length){ctx.frames.shift()(time);time+=80}
  await done;
  assert.ok(parts.length>1);
  assert.equal(parts.at(-1),'先停下追问😀，围绕原事件回顾。');
  assert.ok(parts.every(p=>!p.endsWith('\ud83d')));
  const reduced=[];await ctx.courseRevealReply('立即显示',p=>reduced.push(p),{immediate:true});
  assert.deepEqual(reduced,['立即显示']);
  const hidden=[];
  const pending=ctx.courseRevealReply('后台立即完成',p=>hidden.push(p));
  ctx.document.hidden=true;ctx.listeners.visibilitychange();await pending;
  assert.equal(hidden.at(-1),'后台立即完成');
  console.log('Progressive reply: chunks, Unicode, reduced motion, background completion passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
