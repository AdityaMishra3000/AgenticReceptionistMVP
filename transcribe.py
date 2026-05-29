import os
import io
import logging
import numpy as np
import torch
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from faster_whisper import WhisperModel
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# ── Load Whisper model once at startup ───────────────────────────────────────
# large-v3-turbo is best balance of speed + accuracy for Indian languages
# device="cpu" if no GPU, compute_type="int8" keeps it fast on CPU
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")

logger.info(f"Loading Whisper model: {WHISPER_MODEL} ...")
whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
logger.info("Whisper model loaded.")

# ── Load Silero VAD once at startup ───────────────────────────────────────────
logger.info("Loading Silero VAD...")
vad_model, vad_utils = torch.hub.load(
    repo_or_dir="snakers4/silero-vad",
    model="silero_vad",
    force_reload=False,
    trust_repo=True,
)
(get_speech_timestamps, _, read_audio, *_) = vad_utils
logger.info("Silero VAD loaded.")


# ── Helper: check if audio has speech ────────────────────────────────────────

def has_speech(audio_path: str) -> bool:
    """Returns True if Silero VAD detects any speech in the file."""
    try:
        wav = read_audio(audio_path, sampling_rate=16000)
        timestamps = get_speech_timestamps(wav, vad_model, sampling_rate=16000)
        return len(timestamps) > 0
    except Exception as e:
        logger.warning(f"VAD check failed: {e}, proceeding without VAD")
        return True  # if VAD fails, still try to transcribe


# ── Transcribe endpoint ───────────────────────────────────────────────────────

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Upload an audio file, get back a transcript.
    Accepts: .wav, .mp3, .ogg, .m4a, .webm — anything ffmpeg can read.
    Returns: { "transcript": "...", "language": "...", "has_speech": true/false }
    """
    # Save uploaded file to a temp location
    suffix = os.path.splitext(file.filename)[-1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # VAD check first
        speech_detected = has_speech(tmp_path)

        if not speech_detected:
            logger.info("VAD: no speech detected in file")
            return {
                "transcript": "",
                "language": None,
                "has_speech": False,
                "message": "No speech detected in audio"
            }

        # Transcribe with Whisper
        segments, info = whisper.transcribe(
            tmp_path,
            beam_size=5,
            language=None,           # auto-detect language
            task="transcribe",
            vad_filter=True,         # whisper's built-in VAD as second pass
            vad_parameters=dict(
                min_silence_duration_ms=500
            ),
        )

        transcript = " ".join(seg.text.strip() for seg in segments).strip()
        detected_lang = info.language
        lang_prob = round(info.language_probability, 2)

        logger.info(f"Transcript: {transcript}")
        logger.info(f"Language: {detected_lang} (confidence: {lang_prob})")

        return {
            "transcript": transcript,
            "language": detected_lang,
            "language_confidence": lang_prob,
            "has_speech": True,
        }

    finally:
        os.unlink(tmp_path)  # clean up temp file


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "running",
        "whisper_model": WHISPER_MODEL,
        "device": "cpu",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("transcribe:app", host="0.0.0.0", port=8001, reload=False)
    # note: reload=False because model loading is heavy, don't reload on file change