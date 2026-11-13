"""Local Kokoro TTS server, OpenAI-compatible (/v1/audio/speech).
Point Open WebUI's OpenAI TTS engine at http://127.0.0.1:8880/v1 to use it.
Fully local, no API key. Model files: kokoro-v1.0.onnx and voices-v1.0.bin in KOKORO_DIR.
"""
import io
import os

import numpy as np
import soundfile as sf
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

# Model files live in KOKORO_DIR (set by scripts/start-kokoro.sh), else next to this script.
HERE = os.environ.get('KOKORO_DIR') or os.path.dirname(os.path.abspath(__file__))
ONNX = os.path.join(HERE, 'kokoro-v1.0.onnx')
VOICES = os.path.join(HERE, 'voices-v1.0.bin')
DEFAULT_VOICE = 'af_heart'          # warm US female; see kokoro voice list
VALID_PREFIXES = ('af_', 'am_', 'bf_', 'bm_', 'ef_', 'em_', 'hf_', 'hm_', 'if_', 'im_', 'jf_', 'jm_', 'pf_', 'pm_', 'zf_', 'zm_')

app = FastAPI()
_kokoro = None


def kokoro():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(ONNX, VOICES)
    return _kokoro


class SpeechReq(BaseModel):
    model: str | None = 'kokoro'
    input: str
    voice: str | None = DEFAULT_VOICE
    response_format: str | None = 'wav'
    speed: float | None = 1.0


def synth(text: str, voice: str, speed: float) -> bytes:
    v = voice if voice and voice.startswith(VALID_PREFIXES) else DEFAULT_VOICE
    samples, sr = kokoro().create(text, voice=v, speed=speed or 1.0, lang='en-us')
    buf = io.BytesIO()
    sf.write(buf, np.asarray(samples), sr, format='WAV')
    return buf.getvalue()


@app.post('/v1/audio/speech')
@app.post('/audio/speech')
def speech(req: SpeechReq):
    audio = synth(req.input, req.voice or DEFAULT_VOICE, req.speed or 1.0)
    return Response(content=audio, media_type='audio/wav')


@app.get('/health')
def health():
    return {'status': 'ok', 'model': 'kokoro-v1.0', 'default_voice': DEFAULT_VOICE}


@app.get('/v1/models')
def models():
    return {'object': 'list', 'data': [{'id': 'kokoro', 'object': 'model'}]}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('KOKORO_PORT', '8880')))
