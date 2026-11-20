class NoxCinemaPCM16 extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
    this.frame = [];
    this.frameSamples = 1600;
    this.frameContextTime = null;
  }
  process(inputs, outputs) {
    const input = inputs[0];
    const out = outputs[0];
    if (out) for (const channel of out) channel.fill(0);
    if (!input || !input.length || !input[0].length) return true;
    const length = input[0].length;
    for (let i = 0; i < length; i++) {
      let sample = 0;
      for (let c = 0; c < input.length; c++) sample += input[c][i] || 0;
      sample /= input.length;
      this.sum += sample;
      this.count += 1;
      this.phase += this.targetRate / sampleRate;
      if (this.phase >= 1) {
        this.phase -= 1;
        if (this.frameContextTime === null) this.frameContextTime = currentTime + i / sampleRate;
        const averaged = this.sum / Math.max(1, this.count);
        this.sum = 0; this.count = 0;
        const pcm = Math.max(-1, Math.min(1, averaged));
        this.frame.push(pcm < 0 ? Math.round(pcm * 32768) : Math.round(pcm * 32767));
        if (this.frame.length >= this.frameSamples) {
          const buffer = new ArrayBuffer(this.frame.length * 2);
          const view = new DataView(buffer);
          for (let n = 0; n < this.frame.length; n++) view.setInt16(n * 2, this.frame[n], true);
          this.port.postMessage({ buffer, contextTimeStart: this.frameContextTime }, [buffer]);
          this.frame.length = 0;
          this.frameContextTime = null;
        }
      }
    }
    return true;
  }
}
registerProcessor('nox-cinema-pcm16', NoxCinemaPCM16);
