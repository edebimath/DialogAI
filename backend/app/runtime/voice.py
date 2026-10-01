"""Voice services for browser calls: STT, TTS, VAD and turn-taking, built from agent settings."""

import os
import sys
import threading
from pathlib import Path

from app.core.config import settings as app_settings
from app.runtime.providers import STTSettings, TTSSettings, TurnSettings

WHISPER_MODELS = {
    "large-v3-turbo": "deepdml/faster-whisper-large-v3-turbo-ct2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "medium": "Systran/faster-whisper-medium",
    "small": "Systran/faster-whisper-small",
}

_cuda_ready = False


def setup_cuda_dlls() -> None:
    """faster-whisper on Windows needs the pip-installed cuBLAS/cuDNN DLLs on the search path."""
    global _cuda_ready
    if _cuda_ready or sys.platform != "win32":
        return
    nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        bin_dir = nvidia / sub / "bin"
        if bin_dir.exists():
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]
    _cuda_ready = True


# One Whisper model per (model, device, compute type), shared by all calls: loading takes
# seconds and a second copy would not fit next to the LLM in 8 GB of VRAM.
_whisper_models: dict[tuple[str, str, str], object] = {}
_whisper_lock = threading.Lock()


def _cached_whisper(model: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    key = (model, device, compute_type)
    with _whisper_lock:
        if key not in _whisper_models:
            _whisper_models[key] = WhisperModel(model, device=device, compute_type=compute_type)
        return _whisper_models[key]


def build_stt(cfg: STTSettings):
    """Blocking (loads a model on first use); call it from a worker thread."""
    setup_cuda_dlls()
    from pipecat.services.whisper.stt import WhisperSTTService
    from pipecat.transcriptions.language import Language

    class CachedWhisperSTTService(WhisperSTTService):
        def _load(self):
            model = self._settings.model
            self._model = _cached_whisper(model, self._device, self._compute_type)
            if unsupported := self._unsupported_language():
                raise ValueError(unsupported)

    try:
        language = Language(cfg.language)
    except ValueError:
        language = Language.TR
    device = app_settings.whisper_device
    compute_type = app_settings.whisper_compute_type or ("int8_float16" if device == "cuda" else "int8")
    return CachedWhisperSTTService(
        device=device,
        compute_type=compute_type,
        settings=WhisperSTTService.Settings(
            model=WHISPER_MODELS.get(cfg.model, cfg.model), language=language
        ),
    )


def build_tts(cfg: TTSSettings):
    """Blocking (loads the voice); call it from a worker thread."""
    from pipecat.services.piper.tts import PiperTTSService

    return PiperTTSService(settings=PiperTTSService.Settings(voice=cfg.voice))


def build_vad(turn: TurnSettings):
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams

    # With Smart Turn the VAD only marks pauses and the model decides whether the caller is
    # done, so the pause is kept short; in silence mode the pause itself ends the turn.
    stop_secs = 0.2 if turn.mode == "smart" else turn.vad_stop_secs
    return SileroVADAnalyzer(params=VADParams(stop_secs=stop_secs))


def build_turn_strategies(turn: TurnSettings):
    from pipecat.turns.user_start import TranscriptionUserTurnStartStrategy, VADUserTurnStartStrategy
    from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
    from pipecat.turns.user_turn_strategies import UserTurnStrategies, default_user_turn_stop_strategies

    interrupt = turn.allow_interruptions
    start = [
        VADUserTurnStartStrategy(enable_interruptions=interrupt),
        TranscriptionUserTurnStartStrategy(enable_interruptions=interrupt),
    ]
    if turn.mode == "smart":
        stop = default_user_turn_stop_strategies()
    else:
        stop = [SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=turn.vad_stop_secs)]
    return UserTurnStrategies(start=start, stop=stop)
