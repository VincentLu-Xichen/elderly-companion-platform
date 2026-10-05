const ui = Object.fromEntries(
  [...document.querySelectorAll("[id]")].map((element) => [element.id, element])
);
const runtime = window.ESDS_CONFIG || {};
ui.url.value =
  runtime.wsUrl ||
  `${location.protocol === "https:" ? "wss" : "ws"}://${location.hostname || "localhost"}:8765/v1/device`;
ui.token.value = runtime.deviceToken || "";

let socket = null;
let context = null;
let microphoneStream = null;
let captureNode = null;
let playbackBus = null;
let state = "idle";
let sessionReady = false;
let reconnectTimer = 0;
let reconnectAttempt = 0;
let thinkingAt = 0;
let nextPlayTime = 0;
let playbackStart = 0;
let scheduledSamples = 0;
let generationDone = false;
let drainedSent = false;
let micGateUntil = 0;
let progressTimer = 0;
const sources = new Set();

function log(message) {
  ui.log.textContent = `${new Date().toLocaleTimeString()} ${message}\n${ui.log.textContent}`.slice(0, 6000);
}

function setState(next) {
  state = next;
  ui.state.textContent = `状态：${next}`;
  const labels = {
    listening: "正在听",
    user_speaking: "你正在说话",
    processing: "正在识别和生成共情回复",
    assistant_speaking: "正在播放回复",
    interrupting: "正在停止播放",
  };
  ui.status.textContent = `${labels[next] || next} · 仅使用麦克风`;
  if (next === "processing") thinkingAt = performance.now();
}

async function ensureAudio() {
  if (context && context.state !== "closed") {
    if (context.state === "suspended") await context.resume();
    return;
  }
  context = new AudioContext({ sampleRate: 48000, latencyHint: "interactive" });
  await context.audioWorklet.addModule("./capture-worklet.js");
  playbackBus = context.createGain();
  playbackBus.connect(context.destination);

  const supported = navigator.mediaDevices.getSupportedConstraints();
  const audio = {
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: false,
  };
  if (supported.voiceIsolation) audio.voiceIsolation = true;
  microphoneStream = await navigator.mediaDevices.getUserMedia({ audio });
  const source = context.createMediaStreamSource(microphoneStream);
  captureNode = new AudioWorkletNode(context, "pcm-capture");
  const mute = context.createGain();
  mute.gain.value = 0;
  source.connect(captureNode).connect(mute).connect(context.destination);
  captureNode.port.onmessage = (event) => {
    const playbackLive = sources.size > 0;
    const blocked =
      !sessionReady ||
      state === "processing" ||
      state === "assistant_speaking" ||
      state === "interrupting" ||
      playbackLive ||
      performance.now() < micGateUntil;
    if (!blocked && socket?.readyState === WebSocket.OPEN) {
      socket.send(event.data);
    }
  };
  log("麦克风已开启：AEC/NS 开，AGC 关；未请求摄像头权限");
}

function playPcm(arrayBuffer) {
  if (!context || context.state === "closed") return;
  if (context.state === "suspended") context.resume().catch(() => {});
  const pcm = new Int16Array(arrayBuffer);
  if (!pcm.length) return;
  const buffer = context.createBuffer(1, pcm.length, 24000);
  const output = buffer.getChannelData(0);
  for (let index = 0; index < pcm.length; index += 1) {
    output[index] = pcm[index] / 32768;
  }
  const node = context.createBufferSource();
  node.buffer = buffer;
  node.connect(playbackBus);
  const start = Math.max(context.currentTime + 0.04, nextPlayTime);
  if (!playbackStart) {
    playbackStart = start;
    scheduledSamples = 0;
    generationDone = false;
    drainedSent = false;
  }
  node.start(start);
  nextPlayTime = start + buffer.duration;
  scheduledSamples += pcm.length;
  sources.add(node);
  node.onended = () => {
    sources.delete(node);
    maybeReportDrained();
  };
  if (thinkingAt) {
    ui.latency.textContent = `首音频：${Math.round(performance.now() - thinkingAt)} ms`;
    thinkingAt = 0;
  }
}

function playedMs() {
  if (!playbackStart || !context) return 0;
  const elapsed = Math.max(0, Math.floor((context.currentTime - playbackStart) * 24000));
  return Math.round(Math.min(scheduledSamples, elapsed) / 24);
}

function resetPlayback() {
  nextPlayTime = context?.currentTime || 0;
  playbackStart = 0;
  scheduledSamples = 0;
  generationDone = false;
  drainedSent = false;
}

function flushPlayback() {
  for (const source of sources) {
    try { source.stop(); } catch {}
  }
  sources.clear();
  resetPlayback();
}

function maybeReportDrained() {
  if (
    !generationDone ||
    sources.size ||
    drainedSent ||
    socket?.readyState !== WebSocket.OPEN
  ) return;
  drainedSent = true;
  micGateUntil = performance.now() + 450;
  socket.send(JSON.stringify({
    type: "playback.drained",
    played_ms: playedMs(),
    timestamp_ms: Date.now(),
  }));
  resetPlayback();
}

function handleControl(event) {
  if (event.type === "session.ready") {
    sessionReady = true;
    setState(event.state || "listening");
    const settings = microphoneStream?.getAudioTracks?.()[0]?.getSettings?.() || {};
    socket.send(JSON.stringify({
      type: "client.audio_settings",
      requested: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: false,
      },
      settings,
      user_agent: navigator.userAgent.slice(0, 256),
    }));
  } else if (event.type === "state.changed") {
    setState(event.state);
  } else if (event.type === "emotion.updated") {
    const value = event.emotion || {};
    ui.emotion.textContent = `情绪：${value.label || "—"}`;
    ui.confidence.textContent = `置信度：${Math.round((value.confidence || 0) * 100)}%`;
  } else if (event.type === "transcript.user" && event.final) {
    ui.userText.textContent = event.text || "…";
  } else if (event.type === "transcript.assistant") {
    if (event.final) ui.assistantText.textContent = event.text || "…";
    else ui.assistantText.textContent += event.text || "";
  } else if (event.type === "audio.flush") {
    flushPlayback();
  } else if (event.type === "audio.done") {
    generationDone = event.status !== "cancelled" && event.status !== "canceled";
    maybeReportDrained();
  } else if (event.type === "turn.ignored") {
    log(`本轮未回复：${event.reason}`);
  } else if (event.type === "error") {
    log(`错误 ${event.code}: ${event.message}`);
  }
}

async function connect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = 0;
  }
  ui.connect.disabled = true;
  ui.connect.textContent = "正在连接…";
  await ensureAudio();

  const previous = socket;
  if (previous) {
    previous.onopen = null;
    previous.onmessage = null;
    previous.onerror = null;
    previous.onclose = null;
    if (
      previous.readyState === WebSocket.OPEN ||
      previous.readyState === WebSocket.CONNECTING
    ) {
      previous.close(4000, "manual reconnect");
    }
  }

  const nextSocket = new WebSocket(ui.url.value);
  socket = nextSocket;
  nextSocket.binaryType = "arraybuffer";
  nextSocket.onopen = () => {
    if (socket !== nextSocket) return;
    reconnectAttempt = 0;
    nextSocket.send(JSON.stringify({
      type: "device.hello",
      protocol: "companion-audio/1",
      device_id: `esds-web-${crypto.randomUUID()}`,
      device_type: "esds_web_audio",
      token: ui.token.value || undefined,
      audio: { sample_rate: 24000, channels: 1, format: "pcm16", frame_ms: 20 },
      capabilities: ["audio", "aec"],
    }));
    ui.connect.disabled = false;
    ui.connect.textContent = "重新连接";
    log("WebSocket 已连接");
    clearInterval(progressTimer);
    progressTimer = setInterval(() => {
      if (playbackStart && socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
          type: "playback.progress",
          played_ms: playedMs(),
          timestamp_ms: Date.now(),
        }));
      }
    }, 100);
  };
  nextSocket.onmessage = (message) => {
    if (socket !== nextSocket) return;
    if (message.data instanceof ArrayBuffer) playPcm(message.data);
    else {
      try { handleControl(JSON.parse(message.data)); }
      catch (error) { log(`控制事件解析失败：${error.message}`); }
    }
  };
  nextSocket.onclose = (event) => {
    if (socket !== nextSocket) return;
    socket = null;
    sessionReady = false;
    clearInterval(progressTimer);
    flushPlayback();
    ui.status.textContent = `连接已断开 (${event.code})`;
    scheduleReconnect();
  };
  nextSocket.onerror = () => {
    if (socket === nextSocket) log("WebSocket 连接错误");
  };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  const delay = Math.min(15000, 1000 * 2 ** reconnectAttempt);
  reconnectAttempt += 1;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = 0;
    connect().catch((error) => {
      log(`重连失败：${error.message}`);
      scheduleReconnect();
    });
  }, delay);
}

ui.connect.addEventListener("click", () => {
  connect().catch((error) => {
    ui.connect.disabled = false;
    ui.connect.textContent = "开始语音";
    log(`启动失败：${error.message}`);
  });
});
