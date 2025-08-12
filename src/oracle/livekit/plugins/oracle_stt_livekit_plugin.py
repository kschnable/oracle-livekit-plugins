from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import asyncio

from typing import AsyncIterator

from livekit.agents import stt
from livekit import rtc

from .oracle_stt import OracleSTT


class STT(stt.STT):
    def __init__(
            self,
            *,
            secure: bool = True,
            host: str = None,  # must be specified
            port_number: int = 443,
            compartment_id: str = None, # must be specified
            authentication_configuration_file_spec: str = "~/.oci/config",
            authentication_configuration_name: str = "DEFAULT",
            sample_rate: int = 16000,
            language_code: str = "en-US",
            model_domain: str = "GENERIC",
            is_ack_enabled: bool = False,
            partial_silence_threshold_milliseconds: int = 0,
            final_silence_threshold_milliseconds: int = 2000,
            stabilize_partial_results: bool = "NONE",
            punctuation: str = "NONE",
            customization_ids: list[str] = None,
            should_ignore_invalid_customizations: bool = False,
            return_partial_results: bool = False
            ) -> None:

        capabilities = stt.STTCapabilities(streaming = True, interim_results = return_partial_results)
        super().__init__(capabilities = capabilities)

        self._sample_rate = sample_rate

        self._oracle_stt = OracleSTT(
            secure = secure,
            host = host,
            port_number = port_number,
            compartment_id = compartment_id,
            authentication_configuration_file_spec = authentication_configuration_file_spec,
            authentication_configuration_name = authentication_configuration_name,
            sample_rate = sample_rate,
            language_code = language_code,
            model_domain = model_domain,
            is_ack_enabled = is_ack_enabled,
            partial_silence_threshold_milliseconds = partial_silence_threshold_milliseconds,
            final_silence_threshold_milliseconds = final_silence_threshold_milliseconds,
            stabilize_partial_results = stabilize_partial_results,
            punctuation = punctuation,
            customization_ids = customization_ids,
            should_ignore_invalid_customizations = should_ignore_invalid_customizations,
            return_partial_results = return_partial_results
            )


    async def get_speech_event(self) -> stt.SpeechEvent:
        speech_result_queue = self._oracle_stt.get_speech_result_queue()

        if speech_result_queue.empty():
            return None
        
        speech_result = await speech_result_queue.get()
    
        speech_data = stt.SpeechData(
            language = "multi", # this must be "multi" or 4-second delays will always occur before any tts occurs.
            text = speech_result.text
            )

        speech_event = stt.SpeechEvent(
            type = stt.SpeechEventType.FINAL_TRANSCRIPT if speech_result.is_final else stt.SpeechEventType.INTERIM_TRANSCRIPT,
            alternatives = [speech_data]
            )
        
        return speech_event


    # STT method.
    def stream(self) -> DerivedSTTStream:
        return DerivedSTTStream(self)


    # STT method.
    async def _recognize_impl(self, audio_chunk: bytes) -> stt.SpeechEvent:
        speech_data = stt.SpeechData(
            language = "multi",
            text = "zz"
            )

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[speech_data]
        )


    # STT method.
    def on_start(self, participant_id: str, room_id: str):
        pass


    # STT method.
    def on_stop(self):
        pass


class DerivedSTTStream:
    def __init__(self, oracle_stt_livekit_plugin: STT):
        self._running = True
        self._queue = asyncio.Queue()

        self._oracle_stt_livekit_plugin = oracle_stt_livekit_plugin

        self._audio_resampler = None


    async def __aenter__(self):
        return self


    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._running = False


    def __aiter__(self) -> AsyncIterator[stt.SpeechEvent]:
        return self._event_stream()


    def push_frame(self, frame: rtc.AudioFrame):
        self._queue.put_nowait(frame)


    async def _event_stream(self) -> AsyncIterator[stt.SpeechEvent]:
        while self._running:
            frame = await self._queue.get()

            if frame.sample_rate != self._oracle_stt_livekit_plugin._sample_rate:
                if self._audio_resampler is None:
                    self._audio_resampler = rtc.AudioResampler(
                        input_rate = frame.sample_rate,
                        output_rate = self._oracle_stt_livekit_plugin._sample_rate,
                        quality = rtc.AudioResamplerQuality.HIGH
                        )
                frame = self._audio_resampler.push(frame)

            if isinstance(frame, list):
                frames = frame
            else:
                frames = [frame]

            for frame in frames:
                audio_bytes = frame.data
                self._oracle_stt_livekit_plugin._oracle_stt.add_audio_bytes(audio_bytes)

            while True:
                speech_event = await self._oracle_stt_livekit_plugin.get_speech_event()
                if speech_event is None:
                    break
                yield speech_event
