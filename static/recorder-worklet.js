class RecorderWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input[0];

    if (!channel) return true;

    // Acumular frames hasta que tengamos un tamaño adecuado
    this._buffer.push(new Float32Array(channel));

    if (this._buffer.length >= 48) { // 48 * 256 ≈ 12288 muestras (≈ 128 ms)
      const samples = this._buffer.length * 256;
      const pcm = new Int16Array(samples);

      let offset = 0;
      for (const chunk of this._buffer) {
        for (let i = 0; i < chunk.length; i++, offset++) {
          pcm[offset] = chunk[i] * 0x7fff;
        }
      }

      this.port.postMessage(pcm.buffer);
      this._buffer = [];
    }

    return true;
  }
}

registerProcessor("recorder-worklet", RecorderWorklet);
