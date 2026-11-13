# Performance notes

Model: Qwen3.8-27B in the `Youssofal/Qwen3.8-27B-MTPLX-Optimized-Speed` pack (4-bit, with an
MTP head), served by mtplx on an M5 Pro with 64 GB of unified memory. Numbers are from
September 2026 measurements on that one machine; treat them as one data point, not a benchmark.

## Decode speed by speculative-decoding depth

Raw data: `eval/results/mtp_depth_ab.json` (1,200-token generations, same prompt).

| Mode | Decode tok/s | Draft acceptance (accepted / drafted, by depth) |
|---|---|---|
| Plain autoregressive | 13.7, 13.6 | n/a |
| MTP depth 1 | 22.9 | 562 / 627 |
| MTP depth 2 | 28.4 | 403 / 455, 332 / 454 |
| MTP depth 3 | 32.5, 32.1 | 339 / 386, 267 / 386, 203 / 386 |

Short bursts at depth 3 reached 37.5 tok/s in the speed audit. The first measurement after the
build was 31.8 tok/s against 13.2 plain, 2.41x.

A sustained 6,000-token generation at the highest reasoning effort ran at 31.3 tok/s overall,
35.4 tok/s over the first 256 tokens and 30.2 over the last 256
(`eval/results/sustained_6000_tokens.json`). Peak memory in these runs was about 42 GB.

## What limits it

The speed audit (a multi-agent research pass plus live A/B runs, Sep 1 2026) concluded that idle
decode sits at the memory-bandwidth ceiling: each verify round streams about 18.2 GB of weights
at about 250 GB/s, roughly 81 % of the M5 Pro's 307 GB/s, so a round costs 81 to 87 ms at every
depth. No engine flag, kernel, KV-cache setting or runtime swap tested moved decode more than
about 5 %.

Depth 3 is the cap for this architecture.

## Where the time actually went

- **Host contention.** The real-use median was 23.4 tok/s against 37.5 idle. Slow requests
  coincided with other heavy work on the machine (embedding builds, installs, downloads, eval
  runs). Avoiding overlap was worth an estimated 12 to 15 % token-weighted.
- **Prefill of tool schemas.** Cold prompts carrying tools were 9.5k to 15k tokens, of which about
  7.1k were Open WebUI's builtin tool schemas: 16 to 38 seconds before the first token at the
  measured prefill rates. Turning builtin tools off where a persona does not need them was the
  largest single time-to-first-token win.
- **Title generation.** On a serial scheduler, the new-chat title request ran before the user's
  first turn, adding 4 to 9 seconds. Tag and follow-up generation had already been turned off.
- **Memory pressure.** With about 26 tool servers resident, swap ran high and the server logged
  frequent pressure-trim events; a big turn peaked at 62.6 of 64 GB. Trimming the tool roster
  frees an estimated 1.5 to 2.5 GB but does not change tok/s.

## Closed ideas

Measured or researched and found not worth it on this machine: KV-cache quantization (q8 -4 %,
q4 -19 %), prefill chunk size, draft depth above 3, `reasoning_effort: low` as a speed lever,
High Power Mode and fan control, newer or alternative runtimes (llama.cpp GGUF, vllm-metal,
oMLX, mlx-serve), 3-bit packs, Python rebuilds, Metal caps, session-bank caps as a speed lever,
and the small task model as a speed win (titles off gives the same seconds for free).
