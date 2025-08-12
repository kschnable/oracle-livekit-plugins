"""
This module starts up a LiveKit environment to test the LiveKit STT, LLM, and TTS plug-ins.

Author: Keith Schnable (at Oracle Corporation)
Date: 2025-08-12
"""

import sys
import os

plugin_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.append(plugin_path)

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, mcp
from livekit.plugins import (
    deepgram, # only here for re-testing with deepgram
    openai, # only here for re-testing with openai
    cartesia, # only here for re-testing with cartesia
    noise_cancellation, # only here for if interruptions are allowed
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel
#
#  for thinking sound (not supported in console mode).
#
# from livekit.agents.voice.background_audio import BackgroundAudioPlayer

import logging
logger = logging.getLogger(__name__)

from oracle.livekit.plugins import oracle_stt_livekit_plugin
from oracle.livekit.plugins import oracle_llm_livekit_plugin
from oracle.livekit.plugins import oracle_tts_livekit_plugin


load_dotenv()

#
#  to limit logger output.
#
for name in logging.root.manager.loggerDict:
    temp_logger = logging.getLogger(name)
    if name.startswith("oracle.livekit.plugins") or name == "__main__":
        temp_logger.setLevel(logging.ERROR) # ERROR for demos, DEBUG for development / testing.
    else:
        temp_logger.setLevel(logging.ERROR)

#
#  sample tools.
#
from oracle.livekit.plugins.oracle_llm import OracleTool, OracleValue, BACK_END_GEN_AI_LLM, BACK_END_GEN_AI_AGENT
import math


def calculate_factorial(number: int) -> int:
    logger.debug("Additional tool calculate_factorial() called.    number: " + str(number))
    return math.factorial(number)


def get_employee_name_from_employee_id(employee_id: int) -> str:
    logger.debug("Additional tool get_employee_name_from_employee_id() called.    employee_id: " + str(employee_id))
    if employee_id % 2 == 0:
        return "mary stevenson"
    else:
        return "franklin smith"


additional_tools = []


parameters = []
parameter = OracleValue("parameter_integer_value", "The number to find the factorial of.", "number")
parameters.append(parameter)

additional_tool = OracleTool("calculate_factorial", "Calculate the factorial of an number.", calculate_factorial, parameters)
additional_tools.append(additional_tool)


parameters = []
parameter = OracleValue("parameter_integer_value", "The employee id.", "number")
parameters.append(parameter)

additional_tool = OracleTool("get_employee_name_from_employee_id", "Get the employee name from employee id.", get_employee_name_from_employee_id, parameters)
additional_tools.append(additional_tool)


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="Please limit all responses to one relatively short sentence if possible. The initial greeting should be: How can I help you?")


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()

    session = AgentSession(


        # stt = deepgram.STT(model="nova-3", language="multi"),
        stt = oracle_stt_livekit_plugin.STT(
            host = "realtime.aiservice.us-ashburn-1.oci.oraclecloud.com",
            compartment_id = "ocid1.tenancy.oc1..aaaaaaaavhztk6bkuogd5w3nufs5dzts6dfob4nqxedvgbsi7qadonat76fa",
            partial_silence_threshold_milliseconds = 750,
            final_silence_threshold_milliseconds = 750
            ),


        # llm = openai.LLM(model="gpt-4o-mini"),
        llm = oracle_llm_livekit_plugin.LLM(
            host = "inference.generativeai.us-chicago-1.oci.oraclecloud.com",
            additional_tools = additional_tools,

            back_end = BACK_END_GEN_AI_LLM,
            compartment_id = "ocid1.tenancy.oc1..aaaaaaaahzy3x4boh7ipxyft2rowu2xeglvanlfewudbnueugsieyuojkldq",
            model_type = "GENERIC",
            model_name = "openai.gpt-4.1-mini",
            # model_name = "openai.gpt-4o-2024-11-20"
            ),
        # llm = oracle_llm_livekit_plugin.LLM(
        #     host = "agent-runtime.generativeai.us-chicago-1.oci.oraclecloud.com",
        #     additional_tools = additional_tools,

        #     back_end = BACK_END_GEN_AI_AGENT,
        #     agent_endpoint_id = "ocid1.genaiagentendpoint.oc1.us-chicago-1.amaaaaaa74akfsaacw4uugwrfzyjmiefeubuholl5evy5haldwopprbckyja"
        #     ),


        # tts = cartesia.TTS(),
        tts = oracle_tts_livekit_plugin.TTS(
            host = "speech.aiservice-preprod.uk-london-1.oci.oraclecloud.com",
            compartment_id = "ocid1.tenancy.oc1..aaaaaaaavhztk6bkuogd5w3nufs5dzts6dfob4nqxedvgbsi7qadonat76fa",
            #
            #  possible voices as of 2025-07-24: Brian, Jack, Ethan, Richard, Victoria, Cindy, Amanda, Stephanie, Henry, Mark, Phil,
            #                                    Rachel, Steve, Ashley, Mary, Stacy, Adam, Chris, Annabelle, Brad, Teresa, Kevin,
            #                                    Megan, Bob, Laura, Grace, Paul, Olivia
            #
            voice = "Victoria",
            audio_cache_file_path = "/Users/kschnabl/temp/livekit_tts_plugin_cache",
            audio_cache_maximum_text_length = 100
            ),


        # Monitoring Events: LiveKit emits various events such as user_started_speaking, user_stopped_speaking,
        # agent_started_speaking, and agent_stopped_speaking. By subscribing to these events, your STT plugin can
        # gain insights into the current speaking state and adjust its behavior accordingly.
        #
        #  to allow for barge-ins / interruptions set this to True (but also do not set the noise_cancellation parameter below).
        #
        allow_interruptions = False,


        #
        #  sample mcp server.
        #
        mcp_servers = [mcp.MCPServerHTTP(url="http://localhost:8000/sse")],


        vad = silero.VAD.load(),
        turn_detection = MultilingualModel(),


        #
        #  this needs to be set higher than the default of 3 because one utterance / request could involve many tool calls.
        #
        max_tool_steps = 20
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results

            #
            #  commenting this out seems to help with barge-ins / interruptions.
            #
            # noise_cancellation=noise_cancellation.BVC()
        ),
    )

    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )

    #
    #  for thinking sound (not supported in console mode).
    #
    # background_audio_player = BackgroundAudioPlayer()
    # await background_audio_player.start(room = ctx.room, agent_session = session)
    # handle = background_audio_player.play("file:///Users/kschnabl/src/AIAgent/waiting.mp3", loop = True)


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
