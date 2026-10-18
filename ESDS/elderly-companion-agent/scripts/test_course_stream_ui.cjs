/* Protocol tests: split UTF-8/SSE frames, server errors, and missing terminal results. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const context = vm.createContext({ TextDecoder, Error, JSON });
vm.runInContext(fs.readFileSync(path.join(__dirname, "../webapp/static/cbt_course/stream.js"), "utf8"), context);

async function request(raw, width) {
  const bytes = new TextEncoder().encode(raw);
  context.fetch = async () => ({ ok: true, headers: new Headers({"content-type": "text/event-stream"}), body: new ReadableStream({
    start(controller) {
      for (let index = 0; index < bytes.length; index += width) controller.enqueue(bytes.slice(index, index + width));
      controller.close();
    }
  }) });
  const parts = [];
  const result = await context.courseStreamRequest("/offline", {}, (text) => parts.push(text), "offline-csrf");
  return { result, parts };
}

(async () => {
  const events = [ {type:"start"}, {type:"reply_delta",text:"先听您说😀"}, {type:"reply_delta",text:"\n再核对。"},
    {type:"result",data:{reply:"完整且已保存",course:{current_step:"learn"}}} ];
  const raw = events.map((event) => "data: " + JSON.stringify(event) + "\r\n\r\n").join("");
  for (const width of [1, 2, 11, 1000]) {
    const {result, parts} = await request(raw, width);
    assert.equal(parts.join(""), "先听您说😀\n再核对。");
    assert.equal(result.reply, "完整且已保存");
  }
  await assert.rejects(request('data: {"type":"reply_delta","text":"半句话"}\n\n', 1), /连接中断/);
  await assert.rejects(request('data: {"type":"error","message":"本轮失败"}\n\n', 3), /本轮失败/);
  console.log("Course stream frontend protocol: 6 checks passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
