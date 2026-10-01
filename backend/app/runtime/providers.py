"""Provider registry: agent voice settings -> Pipecat services.

Adding a provider (cloud or self-hosted) means adding one builder here; the settings panel
lists what PROVIDERS exposes.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings as app_settings


class LLMSettings(BaseModel):
    provider: Literal["ollama", "google"] = "ollama"
    # Any model the provider serves (other Ollama models may be pulled), but only a model name.
    model: str = Field(default="qwen3:8b", pattern=r"^[A-Za-z0-9._:/-]{1,100}$")
    temperature: float | None = Field(default=None, ge=0, le=2)


class STTSettings(BaseModel):
    provider: Literal["whisper"] = "whisper"
    model: str = "large-v3-turbo"
    language: str = Field(default="tr", pattern=r"^[a-z]{2}$")

    @field_validator("model")
    @classmethod
    def known_model(cls, model: str) -> str:
        # The name becomes a model download or a local path; only listed models are loaded.
        if model not in PROVIDERS["stt"]["whisper"]["models"]:
            raise ValueError(f"Bilinmeyen STT modeli: {model}")
        return model


class TTSSettings(BaseModel):
    provider: Literal["piper"] = "piper"
    voice: str = "tr_TR-dfki-medium"

    @field_validator("voice")
    @classmethod
    def known_voice(cls, voice: str) -> str:
        if voice not in PROVIDERS["tts"]["piper"]["voices"]:
            raise ValueError(f"Bilinmeyen ses: {voice}")
        return voice


class TurnSettings(BaseModel):
    # smart: Smart Turn model decides whether the caller finished; silence: a fixed pause does.
    mode: Literal["smart", "silence"] = "smart"
    vad_stop_secs: float = Field(default=0.8, ge=0.2, le=3)
    allow_interruptions: bool = True


class AgentSettings(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    turn: TurnSettings = Field(default_factory=TurnSettings)


PROVIDERS: dict[str, dict[str, Any]] = {
    "llm": {
        "ollama": {"label": "Ollama (yerel)", "models": ["qwen3:8b"], "needs_key": False},
        "google": {
            "label": "Google Gemini",
            "models": ["gemini-2.5-flash"],
            "needs_key": True,
        },
    },
    "stt": {
        "whisper": {"label": "Whisper (yerel)", "models": ["large-v3-turbo", "large-v3", "medium", "small"]}
    },
    "tts": {"piper": {"label": "Piper (yerel)", "voices": ["tr_TR-dfki-medium"]}},
}


class ProviderError(Exception):
    pass


def build_llm(cfg: LLMSettings):
    common: dict[str, Any] = {"model": cfg.model}
    if cfg.temperature is not None:
        common["temperature"] = cfg.temperature

    if cfg.provider == "ollama":
        from pipecat.services.ollama.llm import OLLamaLLMService

        return OLLamaLLMService(
            base_url=app_settings.ollama_openai_url,
            # Qwen3's thinking mode adds seconds per turn; a phone call can't wait for it.
            settings=OLLamaLLMService.Settings(**common, extra={"reasoning_effort": "none"}),
        )
    if cfg.provider == "google":
        if not app_settings.google_api_key:
            raise ProviderError("Gemini için GOOGLE_API_KEY tanımlı değil.")
        from pipecat.services.google.llm import GoogleLLMService

        return GoogleLLMService(
            api_key=app_settings.google_api_key, settings=GoogleLLMService.Settings(**common)
        )
    raise ProviderError(f"Bilinmeyen LLM sağlayıcısı: {cfg.provider}")
