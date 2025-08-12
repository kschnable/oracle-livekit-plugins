"""
This module is the Oracle LiveKit LLM plug-in.

Author: Keith Schnable (at Oracle Corporation)
Date: 2025-08-12
"""

from __future__ import annotations

from livekit.agents import llm, utils
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions
from livekit.plugins.openai.utils import to_fnc_ctx

import copy

import json

from .oracle_llm import OracleLLM, OracleLLMContent, OracleTool, OracleValue, ROLE_SYSTEM, ROLE_ASSISTANT, CONTENT_TYPE_STRING, TOOL_CALL_PREFIX, TOOL_CALL_DESCRIPTION, BACK_END_GEN_AI_LLM


class LLM(llm.LLM):
    """
    The Oracle LiveKit LLM plug-in class. This derives from livekit.agents.llm.LLM.
    """

    def __init__(
        self,
        *,

        secure: bool = True,
        host: str = None, # must be specified
        port_number: int = 443,
        
        additional_tools: list[OracleTool] = None,

        back_end: str = BACK_END_GEN_AI_LLM, # must be BACK_END_GEN_AI_LLM or BACK_END_GEN_AI_AGENT

        # these apply only if back_end == BACK_END_GEN_AI_LLM
        compartment_id: str = None, # must be specified
        authentication_configuration_file_spec: str = "~/.oci/config",
        authentication_configuration_name: str = "DEFAULT",
        model_type: str = "GENERIC", # must be "GENERIC" or "COHERE"
        model_id: str = None, # must be specified or model_name must be specified
        model_name: str = None, # must be specified or model_id must be specified
        maximum_number_of_tokens: int = None,
        temperature: float = None,
        top_p: float = None,
        top_k: int = None,
        frequency_penalty: float = None,
        presence_penalty: float = None,
        seed: int = None,

        # these apply only if back_end == BACK_END_GEN_AI_AGENT
        agent_endpoint_id: str = None # must be specified

        ) -> None:

        super().__init__()

        self._oracle_llm = OracleLLM(

            secure = secure,
            host = host,
            port_number = port_number,

            back_end = back_end,

            compartment_id = compartment_id,
            authentication_configuration_file_spec = authentication_configuration_file_spec,
            authentication_configuration_name = authentication_configuration_name,
            model_type = model_type,
            model_id = model_id,
            model_name = model_name,
            maximum_number_of_tokens = maximum_number_of_tokens,
            temperature = temperature,
            top_p = top_p,
            top_k = top_k,
            frequency_penalty = frequency_penalty,
            presence_penalty = presence_penalty,
            seed = seed,

            agent_endpoint_id = agent_endpoint_id

            )
        
        self.additional_tools = additional_tools

        #
        #  currently this is never cleaned up because it appears that the past tool calls may
        #  always be needed to construct the entire conversation history. if this is not actually
        #  the case, theoretically old keys that are no longer referenced should be removed.
        #
        self._call_id_to_tool_call_dictionary = {}


    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        tools = None,
        tool_choice = None,
        extra_kwargs = None
        ) -> DerivedLLMStream:
        return DerivedLLMStream(oracle_llm_livekit_plugin = self, chat_ctx = chat_ctx, conn_options = conn_options, tools = tools)


class DerivedLLMStream(llm.LLMStream):
    """
    The LLM stream class. This derives from livekit.agents.llm.LLMStream.
    """

    def __init__(
        self,
        *,
        oracle_llm_livekit_plugin: LLM,
        chat_ctx: llm.ChatContext,
        conn_options: None,
        tools: None
        ) -> None:
        super().__init__(oracle_llm_livekit_plugin, chat_ctx = chat_ctx, tools = None, conn_options = conn_options)

        self._oracle_llm_livekit_plugin = oracle_llm_livekit_plugin

        self._tools = DerivedLLMStream.convert_tools(oracle_llm_livekit_plugin.additional_tools, tools)


    async def _run(self) -> None:
        oracle_llm_content_list = []

        for chat_message in self._chat_ctx._items:
            if chat_message.type == "message":
                role = chat_message.role
                for message in chat_message.content:
                    oracle_llm_content = OracleLLMContent(message, CONTENT_TYPE_STRING, role)
                    oracle_llm_content_list.append(oracle_llm_content)

            elif chat_message.type == "function_call_output":
                call_id = chat_message.call_id

                tool_call = self._oracle_llm_livekit_plugin._call_id_to_tool_call_dictionary.get(call_id)

                if tool_call is not None:
                    output_json = json.loads(chat_message.output)
                    message = output_json["text"]

                    oracle_llm_content = OracleLLMContent(tool_call, CONTENT_TYPE_STRING, ROLE_ASSISTANT)
                    oracle_llm_content_list.append(oracle_llm_content)

                    oracle_llm_content = OracleLLMContent("The function result of " + tool_call + " is: " + message, CONTENT_TYPE_STRING, ROLE_SYSTEM)
                    oracle_llm_content_list.append(oracle_llm_content)

        response_messages = self._oracle_llm_livekit_plugin._oracle_llm.run(oracle_llm_content_list = oracle_llm_content_list, tools = self._tools)

        if len(response_messages) > 0:
            if len(response_messages) == 1 and response_messages[0].startswith(TOOL_CALL_PREFIX):
                tool_call = response_messages[0]

                function_name, function_parameters = DerivedLLMStream.get_name_and_arguments_from_tool_call(tool_call)

                tool = None
                for temp_tool in self._tools:
                    if temp_tool.function is None:
                        if temp_tool.name == function_name and len(temp_tool.parameters) == len(function_parameters):
                            tool = temp_tool

                if tool is None:
                    raise Exception("Unknown function name: " + function_name + " in " + TOOL_CALL_DESCRIPTION + " response message: " + tool_call + ".")

                function_parameters_text = "{"
                for i in range(len(function_parameters)):
                    parameter = tool.parameters[i]
                    if i > 0:
                        function_parameters_text += ","
                    function_parameters_text += "\"" + parameter.name + "\":"
                    if parameter.type == "string":
                        function_parameters_text += "\""
                    function_parameters_text += str(function_parameters[i])
                    if parameter.type == "string":
                        function_parameters_text += "\""
                function_parameters_text += "}"

                call_id = utils.shortuuid()

                self._oracle_llm_livekit_plugin._call_id_to_tool_call_dictionary[call_id] = tool_call

                function_tool_call = llm.FunctionToolCall(
                     name = function_name,
                     arguments = function_parameters_text,
                     call_id = call_id
                    )
                
                choice_delta = llm.ChoiceDelta(
                    role = "assistant",
                    content = None,
                    tool_calls = [function_tool_call]
                    )
                
                chat_chunk = llm.ChatChunk(
                    id = utils.shortuuid(),
                    delta = choice_delta,
                    usage = None
                    )
                
                self._event_ch.send_nowait(chat_chunk)

            else:
                chat_chunk = llm.ChatChunk(
                    id = utils.shortuuid(),
                    delta = llm.ChoiceDelta(content = response_messages[0], role = ROLE_ASSISTANT),
                    )

                self._event_ch.send_nowait(chat_chunk)


    @staticmethod
    def convert_tools(additional_tools, livekit_mcp_tools):
        tools = []

        if additional_tools is not None:
            for additional_tool in additional_tools:
                tools.append(copy.deepcopy(additional_tool))

        if livekit_mcp_tools is not None:
            function_contexts = to_fnc_ctx(livekit_mcp_tools)

            for function_context in function_contexts:
                type = function_context["type"]
                if type == "function":
                    function = function_context["function"]

                    function_name = function["name"]
                    function_description = function["description"]
                    if function_description == None or len(function_description) == 0:
                        function_description = function_name
                    function_function = None

                    function_parameters = function["parameters"]

                    parameters = []
                    for property_key, property_value in function_parameters["properties"].items():
                        parameter_name = property_key
                        parameter_description = property_value["title"]
                        parameter_type = property_value["type"]

                        parameter = OracleValue(parameter_name, parameter_description, parameter_type)
                        parameters.append(parameter)

                    tool = OracleTool(function_name, function_description, function_function, parameters)
                    tools.append(tool)

        if len(tools) == 0:
            return None
        
        return tools
    

    def get_name_and_arguments_from_tool_call(tool_call):
        tool_call = tool_call[len(TOOL_CALL_PREFIX):].strip()

        function_name, function_parameters = OracleLLM.parse_function_call(tool_call, TOOL_CALL_DESCRIPTION)

        return function_name, function_parameters
