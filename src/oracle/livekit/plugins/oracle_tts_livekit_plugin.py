from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import asyncio

from livekit.agents import tts, utils
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.rtc import AudioFrame

from .oracle_tts import OracleTTS
from .audio_cache import AudioCache


REQUIRED_LIVE_KIT_AUDIO_RATE = 24000  
REQUIRED_LIVE_KIT_AUDIO_CHANNELS = 1
REQUIRED_LIVE_KIT_AUDIO_BITS = 16


class TTS(tts.TTS):
    def __init__(
        self,
        *,
        secure: bool = True,
        host: str = None, # must be specified
        port_number: int = 443,
        compartment_id: str = None, # must be specified
        authentication_configuration_file_spec: str = "~/.oci/config",
        authentication_configuration_name: str = "DEFAULT",
        voice: str = "Victoria",
        audio_cache_file_path: str = None,
        audio_cache_maximum_text_length: int = 100
        ) -> None:

        capabilities = tts.TTSCapabilities(streaming = False)

        super().__init__(capabilities = capabilities, sample_rate = REQUIRED_LIVE_KIT_AUDIO_RATE, num_channels = REQUIRED_LIVE_KIT_AUDIO_CHANNELS)

        self._oracle_tts = OracleTTS(
            secure = secure,
            host = host,
            port_number = port_number,
            compartment_id = compartment_id,
            authentication_configuration_file_spec = authentication_configuration_file_spec,
            authentication_configuration_name = authentication_configuration_name,
            voice = voice,
            sample_rate = REQUIRED_LIVE_KIT_AUDIO_RATE
            )
        
        if audio_cache_file_path is None:
            self._audio_cache = None
        else:
            self._audio_cache = AudioCache(audio_cache_file_path = audio_cache_file_path)
            self._voice = voice
            self._audio_cache_maximum_text_length = audio_cache_maximum_text_length


    def synthesize(self, text: str, *, conn_options: DEFAULT_API_CONNECT_OPTIONS) -> DerivedTTSChunkedStream:
        return DerivedTTSChunkedStream(tts = self, text = text, conn_options = conn_options)


class DerivedTTSChunkedStream(tts.ChunkedStream):
    def __init__(self, *, tts: tts.TTS, text: str, conn_options: DEFAULT_API_CONNECT_OPTIONS) -> None:
        super().__init__(tts = tts, input_text = text, conn_options = conn_options)

        self._oracle_tts_livekit_plugin = tts

        
    async def _run(self) -> None:
        if self._oracle_tts_livekit_plugin._audio_cache is not None:
            audio_bytes = self._oracle_tts_livekit_plugin._audio_cache.get_audio_bytes(
                text = self._input_text,
                voice = self._oracle_tts_livekit_plugin._voice,
                audio_rate = REQUIRED_LIVE_KIT_AUDIO_RATE,
                audio_channels = REQUIRED_LIVE_KIT_AUDIO_CHANNELS,
                audio_bits = REQUIRED_LIVE_KIT_AUDIO_BITS)

        if audio_bytes is None:
            audio_bytes = await self._oracle_tts_livekit_plugin._oracle_tts.synthesize_speech(text = self._input_text)

            if audio_bytes is not None and self._oracle_tts_livekit_plugin._audio_cache is not None and \
                len(self._input_text) <= self._oracle_tts_livekit_plugin._audio_cache_maximum_text_length:
                self._oracle_tts_livekit_plugin._audio_cache.set_audio_bytes(
                    text = self._input_text,
                    voice = self._oracle_tts_livekit_plugin._voice,
                    audio_rate = REQUIRED_LIVE_KIT_AUDIO_RATE,
                    audio_channels = REQUIRED_LIVE_KIT_AUDIO_CHANNELS,
                    audio_bits = REQUIRED_LIVE_KIT_AUDIO_BITS,
                    audio_bytes = audio_bytes)


        if audio_bytes != None:
            request_id = utils.shortuuid()
            emitter = tts.SynthesizedAudioEmitter(event_ch = self._event_ch, request_id = request_id)

            number_of_samples = int(len(audio_bytes) / 2 / REQUIRED_LIVE_KIT_AUDIO_CHANNELS)

            samples_per_channel = int(number_of_samples / REQUIRED_LIVE_KIT_AUDIO_CHANNELS)

            audio_frame = AudioFrame(audio_bytes, REQUIRED_LIVE_KIT_AUDIO_RATE, REQUIRED_LIVE_KIT_AUDIO_CHANNELS, samples_per_channel)

            emitter.push(audio_frame)
            emitter.flush()
