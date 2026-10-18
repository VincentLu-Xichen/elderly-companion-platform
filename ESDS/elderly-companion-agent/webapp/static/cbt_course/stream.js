/* Model text is provisional; only a persisted result event updates course records. */
async function courseRevealReply(text, paint, {immediate = false} = {}) {
  const chars = Array.from(text); // Do not split emoji surrogate pairs.
  if (immediate || chars.length < 2) { paint(text); return; }
  const duration = Math.min(1600, Math.max(160, chars.length * 9));
  await new Promise((resolve) => {
    let start, shown = 0, frameId, finished = false;
    function finish() {
      if (finished) return;
      finished = true;
      cancelAnimationFrame(frameId);
      document.removeEventListener("visibilitychange", visibility);
      paint(text); resolve();
    }
    function visibility() { if (document.hidden) finish(); }
    function frame(time) {
      if (finished) return;
      if (document.hidden) { finish(); return; }
      if (start === undefined) start = time;
      const count = Math.min(chars.length, Math.max(1, Math.ceil(chars.length * (time - start) / duration)));
      if (count > shown) { shown = count; paint(chars.slice(0, count).join("")); }
      if (count === chars.length) finish();
      else frameId = requestAnimationFrame(frame);
    }
    document.addEventListener("visibilitychange", visibility);
    frameId = requestAnimationFrame(frame);
  });
}

async function courseStreamRequest(url, payload, onDelta, csrfToken) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "text/event-stream", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : "请求未完成，请稍后重试。");
  }
  if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new Error("回复连接格式异常，请稍后重试。");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
        if (!data) continue;
        const item = JSON.parse(data);
        if (item.type === "reply_delta" && typeof item.text === "string") onDelta(item.text);
        else if (item.type === "error") throw new Error(item.message || "回复中断，请重试这一轮。");
        else if (item.type === "result") {
          if (!item.data?.course || typeof item.data.reply !== "string") throw new Error("课程结果不完整，请重试这一轮。");
          return item.data;
        }
      }
      if (buffer.length > 2000000) throw new Error("回复数据过大，请稍后重试。");
      if (done) throw new Error("回复连接中断。请重试这一轮；已保存的结果会直接恢复。");
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
}
