"""A simulated call: one Pipecat pipeline driven by a compiled flow.

Text mode has no transport, STT or TTS: the caller's messages are appended to the LLM context
directly and the bot's replies are read off the pipeline by the trace observer.
Voice mode runs the same flow over a browser WebRTC connection with local STT/TTS, and records
the call to a WAV file.
"""

import asyncio
import wave
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pipecat.flows import FlowManager
from pipecat.frames.frames import EndFrame, LLMMessagesAppendFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.workers.runner import WorkerRunner

from app.flows.compiler import FlowCompiler
from app.flows.schema import FlowGraph
from app.runtime.context_tidy import ContextTidier
from app.runtime.filters import SpokenTextFilter
from app.runtime.providers import AgentSettings, build_llm
from app.trace.events import Tracer
from app.trace.observer import TraceObserver

START_TIMEOUT_SECS = 30
EMPTY_REPLY_NUDGE = (
    "Arayanın son söylediğine henüz cevap vermedin. Şimdi kısa bir cevap ver ya da uygun "
    "fonksiyonu çağır."
)
Mode = Literal["text", "voice"]


class CallSession:
    def __init__(
        self,
        graph: FlowGraph,
        agent_settings: AgentSettings,
        tracer: Tracer,
        variables: dict[str, Any] | None = None,
        *,
        mode: Mode = "text",
        webrtc_connection=None,
        recording_path: Path | None = None,
    ):
        """
        Args:
            webrtc_connection: A SmallWebRTCConnection with the browser's offer applied (voice).
            recording_path: Where to write the call audio as WAV (voice).
        """
        if mode == "voice" and webrtc_connection is None:
            raise ValueError("Voice sessions need a WebRTC connection")
        self.tracer = tracer
        self.mode = mode
        self._settings = agent_settings
        self._variables = variables or {}
        self._connection = webrtc_connection
        self._recording_path = recording_path
        self._compiler = FlowCompiler(graph, tracer, speak=mode == "voice")
        self._runner: WorkerRunner | None = None
        self._worker: PipelineWorker | None = None
        self._flow_manager: FlowManager | None = None
        self._run_task: asyncio.Task | None = None
        self._started = asyncio.Event()
        self.end_reason: str | None = None

    @property
    def finished(self) -> bool:
        return self._run_task is not None and self._run_task.done()

    async def start(self) -> None:
        llm = build_llm(self._settings.llm)
        context = LLMContext()
        if self.mode == "voice":
            pipeline, aggregator, transport = await self._voice_pipeline(llm, context)
        else:
            aggregator = LLMContextAggregatorPair(context)
            pipeline = Pipeline(
                [aggregator.user(), ContextTidier(), llm, SpokenTextFilter(), aggregator.assistant()]
            )
            transport = None

        self._worker = PipelineWorker(
            pipeline,
            params=PipelineParams(enable_metrics=True),
            observers=[TraceObserver(self.tracer, on_empty_reply=self._on_empty_reply)],
            idle_timeout_secs=None,  # the API enforces a session TTL
            enable_rtvi=False,
        )
        self._flow_manager = FlowManager(
            worker=self._worker,
            llm=llm,
            context_aggregator=aggregator,
            transport=transport,
            global_functions=self._compiler.global_functions(),
        )

        @self._worker.event_handler("on_pipeline_started")
        async def on_started(worker, frame):
            self._started.set()

        self._runner = WorkerRunner(handle_sigint=False)
        await self._runner.add_workers(self._worker)
        self._run_task = asyncio.create_task(self._run())
        await asyncio.wait_for(self._started.wait(), START_TIMEOUT_SECS)

        # Text calls start right away; voice calls once the browser's audio is connected,
        # so the greeting isn't spoken into a connection that isn't there yet.
        if self.mode == "text":
            await self._begin_flow()

    async def _voice_pipeline(self, llm, context):
        from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
        from pipecat.transports.base_transport import TransportParams
        from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

        from app.runtime.voice import build_stt, build_tts, build_turn_strategies, build_vad

        turn = self._settings.turn
        # Model loading blocks; keep it off the event loop.
        stt, tts = await asyncio.gather(
            asyncio.to_thread(build_stt, self._settings.stt),
            asyncio.to_thread(build_tts, self._settings.tts),
        )
        transport = SmallWebRTCTransport(
            webrtc_connection=self._connection,
            params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
        )
        aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                vad_analyzer=build_vad(turn), user_turn_strategies=build_turn_strategies(turn)
            ),
        )
        recorder = AudioBufferProcessor(num_channels=1)

        @recorder.event_handler("on_audio_data")
        async def on_audio_data(processor, audio: bytes, sample_rate: int, num_channels: int):
            if self._recording_path and audio:
                await asyncio.to_thread(self._write_wav, audio, sample_rate, num_channels)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            await recorder.start_recording()
            await self._begin_flow()

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            # stop() waits for the pipeline, which is running this handler: don't await it here.
            asyncio.create_task(self.stop("client_disconnected"))

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                aggregator.user(),
                ContextTidier(),
                llm,
                SpokenTextFilter(),
                tts,
                transport.output(),
                recorder,
                aggregator.assistant(),
            ]
        )
        return pipeline, aggregator, transport

    def _write_wav(self, audio: bytes, sample_rate: int, num_channels: int) -> None:
        self._recording_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(self._recording_path), "wb") as f:
            f.setnchannels(num_channels)
            f.setsampwidth(2)
            f.setframerate(sample_rate)
            f.writeframes(audio)

    async def _on_empty_reply(self, streak: int) -> None:
        """Re-run the LLM once with a nudge; a second empty reply in a row is left alone."""
        await self.tracer.emit("empty_reply", retried=streak == 1)
        if streak == 1 and not self.finished:
            await self._worker.queue_frame(
                LLMMessagesAppendFrame(
                    messages=[{"role": "system", "content": EMPTY_REPLY_NUDGE}], run_llm=True
                )
            )

    async def _begin_flow(self) -> None:
        flow_manager = self._flow_manager
        flow_manager.state.update(self._compiler.initial_state(self._variables))
        await self.tracer.emit("session_started", mode=self.mode, variables=dict(flow_manager.state))
        await flow_manager.initialize(await self._compiler.initial_node(flow_manager.state))

    async def _run(self) -> None:
        try:
            await self._runner.run()
            self.end_reason = self.end_reason or "flow_ended"
        except Exception as e:
            logger.exception("Session pipeline failed")
            self.end_reason = "error"
            await self.tracer.emit("error", message=str(e))
        finally:
            await self.tracer.emit(
                "session_ended", outcome=self.tracer.outcome, reason=self.end_reason
            )

    async def send_user_text(self, text: str, source: str = "text") -> None:
        """Typed (or simulated) caller input; works in voice calls too."""
        if self.finished or self._worker is None:
            return
        await self.tracer.emit("user_message", text=text, source=source)
        await self._worker.queue_frame(
            LLMMessagesAppendFrame(messages=[{"role": "user", "content": text}], run_llm=True)
        )

    async def stop(self, reason: str = "user_hangup") -> None:
        if self._run_task is None or self._run_task.done():
            return
        self.end_reason = self.end_reason or reason
        await self._worker.queue_frame(EndFrame())
        try:
            await asyncio.wait_for(asyncio.shield(self._run_task), 10)
        except asyncio.TimeoutError:
            await self._runner.cancel()
            await self._run_task

    async def wait(self) -> None:
        if self._run_task:
            await self._run_task
