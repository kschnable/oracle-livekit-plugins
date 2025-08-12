"""
This module wraps Oracle's TTS cloud service. While it is used by the Oracle LiveKit TTS plug-in,
it it completely indpendent of LiveKit and could be used in other environments besides LiveKit.

Author: Keith Schnable (at Oracle Corporation)
Date: 2025-08-12
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import uuid

import base64

import asyncio

import oci
from oci.config import from_file
from oci.auth.signers.security_token_signer import SecurityTokenSigner
from oci.ai_speech import AIServiceSpeechClient
from oci.ai_speech.models import TtsOracleConfiguration, TtsOracleTts2NaturalModelDetails, TtsOracleSpeechSettings


class OracleTTS():
    """
    The Oracle TTS class. This class wraps the Oracle TTS service.
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
            voice: str = "Victoria",
            sample_rate: int = 16000
            ) -> None:

        self._parameters = Parameters()
        self._parameters.secure = secure
        self._parameters.host = host
        self._parameters.port_number = port_number
        self._parameters.compartment_id = compartment_id
        self._parameters.authentication_configuration_file_spec = authentication_configuration_file_spec
        self._parameters.authentication_configuration_name = authentication_configuration_name
        self._parameters.voice = voice
        self._parameters.sample_rate = sample_rate

        config = from_file(self._parameters.authentication_configuration_file_spec, self._parameters.authentication_configuration_name)
        with open(config["security_token_file"], "r") as f:
            token = f.readline()
        private_key = oci.signer.load_private_key_from_file(config["key_file"])
        signer = SecurityTokenSigner(token = token, private_key = private_key)

        service_endpoint = ("https" if self._parameters.secure else "http") + "://" + self._parameters.host + ":" + str(self._parameters.port_number)

        self._ai_service_speech_client = AIServiceSpeechClient({}, signer = signer, service_endpoint = service_endpoint)


    async def synthesize_speech(self, *, text: str) -> bytes:
        def sync_call():
            logger.debug(text)

            request_id = short_uuid()

            #
            #  this link may help if ever setting is_stream_enabled = True. this will only noticeably reduce latency
            #  if multiple sentences are passed into synthesize_speech() at a time.
            #
            #  https://confluence.oraclecorp.com/confluence/pages/viewpage.action?pageId=11517257226
            #
            response = self._ai_service_speech_client.synthesize_speech(
                synthesize_speech_details = oci.ai_speech.models.SynthesizeSpeechDetails(
                    text = text,
                    is_stream_enabled = False,
                    compartment_id = self._parameters.compartment_id,
                    configuration = TtsOracleConfiguration(
                        model_family = "ORACLE",
                        model_details = TtsOracleTts2NaturalModelDetails(model_name = "TTS_2_NATURAL", voice_id = self._parameters.voice),
                        speech_settings = TtsOracleSpeechSettings(text_type = "TEXT", sample_rate_in_hz = self._parameters.sample_rate, output_format = "PCM")
                        ),
                    ),
                opc_request_id = request_id
                )
            
            if response is None or response.status != 200:
                return None
            
            #
            #  the data is in .wav file format so remove the 44-byte .wav header.
            #
            audio_bytes = response.data.content[44:]

            return audio_bytes
        
        return await asyncio.to_thread(sync_call) 


@staticmethod
def short_uuid() -> str:
    uuid4 = uuid.uuid4()
    base64EncodedUUID = base64.urlsafe_b64encode(uuid4.bytes)
    return base64EncodedUUID.rstrip(b'=').decode('ascii')


class Parameters:
    """
    The parameters class. This class contains all parameter information for the Oracle TTS class.
    """

    secure: bool
    host: str
    port_number: int
    compartment_id: str
    authentication_configuration_file_spec: str
    authentication_configuration_name: str
    voice: str
    sample_rate: int
