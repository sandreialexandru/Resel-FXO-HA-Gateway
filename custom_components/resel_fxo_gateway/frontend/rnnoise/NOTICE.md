# Third-party: RNNoise (WebAssembly build)

`rnnoise.js` and `rnnoise.wasm` are the Emscripten build of [RNNoise](https://github.com/xiph/rnnoise)
(recurrent-neural-network noise suppression, BSD-3-Clause, Xiph.Org / Mozilla / Jean-Marc Valin)
published by Jitsi as [`@jitsi/rnnoise-wasm`](https://github.com/jitsi/rnnoise-wasm) 0.2.1
(Apache-2.0, see `LICENSE`). They are loaded by the card only when `denoise` is on.
