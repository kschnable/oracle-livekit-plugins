"""
This module wraps Oracle's STT cloud service. While it is used by the Oracle LiveKit STT plug-in,
it it completely indpendent of LiveKit and could be used in other environments besides LiveKit.

Author: Keith Schnable (at Oracle Corporation)
Date: 2025-08-12
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from dataclasses import dataclass

import asyncio

from oci_ai_speech_realtime import RealtimeSpeechClient, RealtimeSpeechClientListener
from oci.ai_speech.models import RealtimeParameters, RealtimeMessageAckAudio, RealtimeMessageConnect, RealtimeMessageError, RealtimeMessageResult
import oci
from oci.config import from_file
from oci.auth.signers.security_token_signer import SecurityTokenSigner


class OracleSTT(RealtimeSpeechClientListener):
    """
    The Oracle STT class. This class wraps the Oracle STT service.
    """

    def __init__(
            self,
            *,
            secure: bool = True,
            host: str = None, # must be specified
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

        self._parameters = Parameters()
        self._parameters.secure = secure
        self._parameters.host = host
        self._parameters.port_number = port_number
        self._parameters.compartment_id = compartment_id
        self._parameters.authentication_configuration_file_spec = authentication_configuration_file_spec
        self._parameters.authentication_configuration_name = authentication_configuration_name
        self._parameters.sample_rate = sample_rate
        self._parameters.language_code = language_code
        self._parameters.model_domain = model_domain
        self._parameters.is_ack_enabled = is_ack_enabled
        self._parameters.partial_silence_threshold_milliseconds = partial_silence_threshold_milliseconds
        self._parameters.final_silence_threshold_milliseconds = final_silence_threshold_milliseconds
        self._parameters.stabilize_partial_results = stabilize_partial_results
        self._parameters.punctuation = punctuation
        self._parameters.customization_ids = customization_ids
        self._parameters.should_ignore_invalid_customizations = should_ignore_invalid_customizations
        self._parameters.return_partial_results = return_partial_results

        self._audio_bytes_queue = asyncio.Queue()
        self._speech_result_queue = asyncio.Queue()

        self._real_time_speech_client = None
        self._connected = False
        
        asyncio.create_task(self.add_audio_bytes_background_task())

        self.real_time_speech_client_open()


    def add_audio_bytes(self, audio_bytes: bytes) -> None:
        self._audio_bytes_queue.put_nowait(audio_bytes)


    def get_speech_result_queue(self) -> asyncio.Queue:
        return self._speech_result_queue
    

    def real_time_speech_client_open(self) -> None:
        self.real_time_speech_client_close()

        config = from_file(self._parameters.authentication_configuration_file_spec, self._parameters.authentication_configuration_name)
        with open(config["security_token_file"], "r") as f:
            token = f.readline()
        private_key = oci.signer.load_private_key_from_file(config["key_file"])
        signer = SecurityTokenSigner(token = token, private_key = private_key)

        real_time_parameters = RealtimeParameters()

        real_time_parameters.encoding = "audio/raw;rate=" + str(self._parameters.sample_rate)
        real_time_parameters.language_code = self._parameters.language_code
        real_time_parameters.model_domain = self._parameters.model_domain
        real_time_parameters.is_ack_enabled = self._parameters.is_ack_enabled
        real_time_parameters.partial_silence_threshold_in_ms = self._parameters.partial_silence_threshold_milliseconds
        real_time_parameters.final_silence_threshold_in_ms = self._parameters.final_silence_threshold_milliseconds
        real_time_parameters.stabilize_partial_results = self._parameters.stabilize_partial_results
        real_time_parameters.punctuation = self._parameters.punctuation

        if self._parameters.customization_ids is not None:
            real_time_parameters.customizations = []
            for customization_id in self._parameters.customization_ids:
                real_time_parameters.customizations.append(
                    {
                        "compartmentId": self._parameters.compartment_id,
                        "customizationId": customization_id
                    }
                    )
            real_time_parameters.should_ignore_invalid_customizations = False

        real_time_speech_client_listener = self

        service_endpoint = ("wss" if self._parameters.secure else "ws") + "://" + self._parameters.host + ":" + str(self._parameters.port_number)

        compartment_id = self._parameters.compartment_id

        self._real_time_speech_client = RealtimeSpeechClient(config, real_time_parameters, real_time_speech_client_listener,
            service_endpoint, signer, compartment_id)
        
        asyncio.create_task(self.connect_background_task())


    def real_time_speech_client_close(self) -> None:
        if self._real_time_speech_client != None:
            self._real_time_speech_client.close()
            self._real_time_speech_client = None
        self._connected = False


    async def connect_background_task(self) -> None:
        await self._real_time_speech_client.connect()
        

    async def add_audio_bytes_background_task(self) -> None:
        while True:
            if self._real_time_speech_client != None and not self._real_time_speech_client.close_flag and self._connected:
                audio_bytes = await self._audio_bytes_queue.get()
                await self._real_time_speech_client.send_data(audio_bytes)
            else:
                await asyncio.sleep(.010)


    # RealtimeSpeechClient method.
    def on_network_event(self, message):
        super_result = super().on_network_event(message)
        self.real_time_speech_client_open()
        return super_result


    # RealtimeSpeechClient method.
    def on_error(self, error: RealtimeMessageError):
        super_result = super().on_error(error)
        self.real_time_speech_client_open()
        return super_result


    # RealtimeSpeechClient method.
    def on_connect(self):
        return super().on_connect()


    # RealtimeSpeechClient method.
    def on_connect_message(self, connectmessage: RealtimeMessageConnect):
        self._connected = True
        return super().on_connect_message(connectmessage)


    # RealtimeSpeechClient method.
    def on_ack_message(self, ackmessage: RealtimeMessageAckAudio):
        return super().on_ack_message(ackmessage)


    # RealtimeSpeechClient method.
    def on_result(self, result: RealtimeMessageResult):
        super_result = super().on_result(result)

        transcription = result["transcriptions"][0]

        is_final = transcription["isFinal"]
        text = transcription["transcription"]

        if is_final:
            log_message = "FINAL"
        else:
            log_message = "PARTIAL"
        log_message += " utterance: " + text
        logger.debug(log_message)

        if is_final or self._parameters.return_partial_results:
            speech_result = SpeechResult(is_final, text)
            self._speech_result_queue.put_nowait(speech_result)

        return super_result


    # RealtimeSpeechClient method.
    def on_close(self, error_code: int, error_message: str):
        return super().on_close(error_code, error_message)


class Parameters:
    """
    The parameters class. This class contains all parameter information for the Oracle STT class.
    """

    secure: bool
    host: str
    port_number: int
    compartment_id: str
    authentication_configuration_file_spec: str
    authentication_configuration_name: str
    sample_rate: int
    language_code: str
    model_domain: str
    is_ack_enabled: bool
    partial_silence_threshold_milliseconds: int
    final_silence_threshold_milliseconds: int
    stabilize_partial_results: bool
    punctuation: str
    customization_ids: list[str]
    should_ignore_invalid_customizations: bool
    return_partial_results: bool


@dataclass
class SpeechResult:
    """
    The speech result class. This class contains all information related to one speech result.
    """

    is_final: bool
    text: str
