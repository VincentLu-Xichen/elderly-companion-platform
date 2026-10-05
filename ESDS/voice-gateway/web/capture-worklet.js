class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 24000;
    this.ratio = sampleRate / this.targetRate;
    this.phase = 0;
    this.pending = [];
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    while (this.phase < channel.length) {
      const start = Math.floor(this.phase);
      const end = Math.min(channel.length, Math.max(start + 1, Math.floor(this.phase + this.ratio)));
      let sum = 0;
      for (let i = start; i < end; i += 1) sum += channel[i];
      const sample = Math.max(-1, Math.min(1, sum / (end - start)));
      this.pending.push(sample < 0 ? sample * 0x8000 : sample * 0x7fff);
      this.phase += this.ratio;
    }
    this.phase -= channel.length;

    while (this.pending.length >= 480) {
      const pcm = new Int16Array(480);
      for (let i = 0; i < pcm.length; i += 1) pcm[i] = this.pending[i];
      this.pending.splice(0, pcm.length);
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);

