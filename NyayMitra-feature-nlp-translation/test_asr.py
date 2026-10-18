import gc
import sys
import threading
import time

import torch
import torchaudio
from transformers import AutoModel

MODEL_NAME = "ai4bharat/indic-conformer-600m-multilingual"
TARGET_SR = 16000

# The checkpoint is ~2.4 GB. It used to be built at import time, which meant
# importing this module pinned that memory for the life of the process -- and
# translate_service imports it, so the service started 2.4 GB heavier before a
# single request arrived. It now loads on first use and is dropped again once it
# has been idle, so the memory goes back to the OS instead of being held.
#
# `_model_lock` is held for the whole of a transcription, not just the load, so
# release_idle_model() can never pull the model out from under a running request.
_model = None
_model_lock = threading.Lock()
_last_used = 0.0


def _ensure_model():
    """Build the checkpoint on first call. Caller must hold `_model_lock`."""
    global _model
    if _model is None:
        print("Loading ASR model (this can take a while on first run)...", flush=True)
        _model = AutoModel.from_pretrained(MODEL_NAME, trust_remote_code=True)
        _model.eval()
        print("ASR model loaded.", flush=True)
    return _model


def release_idle_model(max_idle_seconds: float) -> bool:
    """Unload the ASR model once it has been idle that long.

    Returns True if memory was freed. Never blocks: if a transcription is in
    flight the lock is taken, so this returns False and the reaper tries again
    on its next pass.
    """
    global _model

    if not _model_lock.acquire(blocking=False):
        return False
    try:
        if _model is None:
            return False
        if time.time() - _last_used < max_idle_seconds:
            return False
        _model = None
    finally:
        _model_lock.release()

    gc.collect()
    print(
        f"ASR model released after {max_idle_seconds:.0f}s idle (~2.4 GB freed).",
        flush=True,
    )
    return True


def run_asr(audio: "str | bytes", lang: str, decoding: str = "ctc") -> str:
    # `audio` may be a path or raw bytes: torchcodec accepts both, and passing
    # bytes avoids re-opening a file from disk.
    global _last_used

    with _model_lock:
        current = _ensure_model()
        try:
            wav, sr = torchaudio.load(audio)
            wav = torch.mean(wav, dim=0, keepdim=True)

            if sr != TARGET_SR:
                resampler = torchaudio.transforms.Resample(
                    orig_freq=sr, new_freq=TARGET_SR
                )
                wav = resampler(wav)

            with torch.no_grad():
                transcription = current(wav, lang, decoding)
        finally:
            # Stamped on the way out so a long transcription still counts as use.
            _last_used = time.time()

    return transcription


def transcribe_and_discard(audio_bytes: bytes, lang: str, decoding: str = "ctc") -> str:
    # Decode straight from memory. The earlier temp-file version held the file
    # open with NamedTemporaryFile (exclusive lock on Windows), so torchaudio
    # reopening the same path failed with "Permission denied" and every voice
    # request 500'd. torchcodec takes bytes directly, so no temp file is needed.
    return run_asr(audio_bytes, lang, decoding)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_asr.py <audio_file> <lang_code (hi/mr)>")
        sys.exit(1)

    audio_path = sys.argv[1]
    lang = sys.argv[2]

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    print(f"Transcribing {audio_path} (lang={lang}) from the decoded bytes...\n")
    result = transcribe_and_discard(audio_bytes, lang)

    print("----- TRANSCRIPTION -----")
    print(result)
    print("--------------------------")
