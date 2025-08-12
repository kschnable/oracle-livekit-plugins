"""
This module wraps Oracle's LLM cloud service. While it is used by the Oracle LiveKit LLM plug-in,
it it completely indpendent of LiveKit and could be used in other environments besides LiveKit.

Author: Keith Schnable (at Oracle Corporation)
Date: 2025-08-12
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from dataclasses import dataclass

from typing import Any, Callable

import copy

import ast

import uuid

import oci
from oci.config import from_file
from oci.auth.signers.security_token_signer import SecurityTokenSigner


BACK_END_GEN_AI_LLM = "llm"
BACK_END_GEN_AI_AGENT = "agent"

CONTENT_TYPE_STRING = "string"

ROLE_USER = "user"
ROLE_SYSTEM = "system"
ROLE_ASSISTANT = "assistant"
ROLE_DEVELOPER = "developer"

TOOL_CALL_PREFIX = "TOOL-CALL:"
TOOL_CALL_DESCRIPTION = "tool-call"


class OracleLLM():
    """
    The Oracle LLM class. This class wraps the Oracle LLM service.
    """

    def __init__(
            self,
            *,

            secure: bool = True,
            host: str = None, # must be specified
            port_number: int = 443,

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

        self._parameters = Parameters()

        self._parameters.secure = secure
        self._parameters.host = host
        self._parameters.port_number = port_number

        self._parameters.back_end = back_end

        self._parameters.compartment_id = compartment_id
        self._parameters.authentication_configuration_file_spec = authentication_configuration_file_spec
        self._parameters.authentication_configuration_name = authentication_configuration_name
        self._parameters.model_type = model_type
        self._parameters.model_id = model_id
        self._parameters.model_name = model_name
        self._parameters.maximum_number_of_tokens = maximum_number_of_tokens
        self._parameters.temperature = temperature
        self._parameters.top_p = top_p
        self._parameters.top_k = top_k
        self._parameters.frequency_penalty = frequency_penalty
        self._parameters.presence_penalty = presence_penalty
        self._parameters.seed = seed

        self._parameters.agent_endpoint_id = agent_endpoint_id

        self._number_of_runs = 0

        if self._parameters.back_end == BACK_END_GEN_AI_LLM:
            self.initialize_for_llm()
        else: # if self._parameters.back_end == BACK_END_GEN_AI_AGENT:
            self.initialize_for_agent()


    def initialize_for_llm(self):
        config = from_file(self._parameters.authentication_configuration_file_spec, self._parameters.authentication_configuration_name)
        with open(config["security_token_file"], "r") as f:
            token = f.readline()
        private_key = oci.signer.load_private_key_from_file(config["key_file"])
        signer = SecurityTokenSigner(token = token, private_key = private_key)

        service_endpoint = ("https" if self._parameters.secure else "http") + "://" + self._parameters.host + ":" + str(self._parameters.port_number)

        self._generative_ai_inference_client = oci.generative_ai_inference.GenerativeAiInferenceClient(
            config = {},
            service_endpoint = service_endpoint,
            retry_strategy = oci.retry.NoneRetryStrategy(),
            signer = signer
            )


    def initialize_for_agent(self):
        config = from_file(self._parameters.authentication_configuration_file_spec, self._parameters.authentication_configuration_name)
        with open(config["security_token_file"], "r") as f:
            token = f.readline()
        private_key = oci.signer.load_private_key_from_file(config["key_file"])
        signer = SecurityTokenSigner(token = token, private_key = private_key)

        service_endpoint = ("https" if self._parameters.secure else "http") + "://" + self._parameters.host + ":" + str(self._parameters.port_number)

        self._generative_ai_agent_runtime_client = oci.generative_ai_agent_runtime.GenerativeAiAgentRuntimeClient(
            config = {},
            service_endpoint = service_endpoint,
            retry_strategy = oci.retry.NoneRetryStrategy(),
            signer = signer
            )
        
        id = str(uuid.uuid4())
        
        session_details = oci.generative_ai_agent_runtime.models.CreateSessionDetails(
            display_name = "display_name_for_" + id,
            description = "description_for_" + id
            )

        response = self._generative_ai_agent_runtime_client.create_session(
            agent_endpoint_id = self._parameters.agent_endpoint_id,
            create_session_details = session_details
            )
        self._session_id = response.data.id


    #
    #  each role must be one of: ROLE_USER, ROLE_SYSTEM, ROLE_ASSISTANT, or ROLE_DEVELOPER.
    #
    def run(self, *, oracle_llm_content_list: list[OracleLLMContent] = [], tools: list[OracleTool] = None) -> list[str]:
        if self._parameters.back_end == BACK_END_GEN_AI_LLM:
            response_messages = self.run_for_llm(oracle_llm_content_list = oracle_llm_content_list, tools = tools)
        else: # if self._parameters.back_end == BACK_END_GEN_AI_AGENT:
            response_messages = self.run_for_agent(oracle_llm_content_list = oracle_llm_content_list, tools = tools)
        
        self._number_of_runs += 1

        return response_messages
    

    def run_for_llm(self, *, oracle_llm_content_list: list[OracleLLMContent] = [], tools: list[OracleTool] = None) -> list[str]:
        while True:
            temp_message_list = []
            temp_messages = ""

            tool_descriptions = OracleLLM.get_tool_descriptions(tools)
            if tool_descriptions is not None:
                text_content = oci.generative_ai_inference.models.TextContent()
                text_content.text = tool_descriptions

                message = oci.generative_ai_inference.models.Message()
                message.role = ROLE_SYSTEM.upper() # it seems "GENERIC" requires that roles be in uppercase.
                message.content = [text_content]

                temp_message_list.append(message)

                if len(temp_messages) > 0:
                    temp_messages += "\n"

                temp_messages += tool_descriptions

            for oracle_llm_content in oracle_llm_content_list:
                if oracle_llm_content.content_type == CONTENT_TYPE_STRING:
                    text_content = oci.generative_ai_inference.models.TextContent()
                    text_content.text = oracle_llm_content.content_data

                    message = oci.generative_ai_inference.models.Message()
                    message.role = oracle_llm_content.role.upper() # it seems "GENERIC" requires that roles be in uppercase.
                    message.content = [text_content]

                    temp_message_list.append(message)

                    if len(temp_messages) > 0:
                        temp_messages += "\n"

                    temp_messages += oracle_llm_content.content_data

            if self._parameters.model_type == "GENERIC":
                chat_request = oci.generative_ai_inference.models.GenericChatRequest()
                chat_request.messages = temp_message_list

            elif self._parameters.model_type == "COHERE":
                chat_request = oci.generative_ai_inference.models.CohereChatRequest()
                chat_request.message = temp_messages

            if self._parameters.maximum_number_of_tokens is not None:
                chat_request.max_tokens = self._parameters.maximum_number_of_tokens
            if self._parameters.temperature is not None:
                chat_request.temperature = self._parameters.temperature
            if self._parameters.frequency_penalty is not None:
                chat_request.frequency_penalty = self._parameters.frequency_penalty
            if self._parameters.presence_penalty is not None:
                chat_request.presence_penalty = self._parameters.presence_penalty
            if self._parameters.top_p is not None:
                chat_request.top_p = self._parameters.top_p
            if self._parameters.top_k is not None:
                chat_request.top_k = self._parameters.top_k
            if self._parameters.seed is not None:
                chat_request.seed = self._parameters.seed

            serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(
                model_id = self._parameters.model_name if self._parameters.model_id is None else self._parameters.model_id
                )

            chat_details = oci.generative_ai_inference.models.ChatDetails()
            chat_details.serving_mode = serving_mode
            chat_details.chat_request = chat_request
            chat_details.compartment_id = self._parameters.compartment_id

            chat_response = self._generative_ai_inference_client.chat(chat_details)

            if self._parameters.model_type == "GENERIC":
                response_messages = []
                for temp_content in chat_response.data.chat_response.choices[0].message.content:
                    response_messages.append(temp_content.text)
            elif self._parameters.model_type == "COHERE":
                response_messages = [chat_response.data.chat_response.text]

            oracle_llm_content_list = copy.deepcopy(oracle_llm_content_list)

            number_of_calls = 0

            for response_message in response_messages:
                if TOOL_CALL_PREFIX in response_message:
                    if response_message.find(TOOL_CALL_PREFIX, 1) != -1:
                        raise Exception("Unexpectedly received a response message with an embedded " + TOOL_CALL_DESCRIPTION + ".")
                    number_of_calls += 1

            if number_of_calls > 1 or (number_of_calls == 1 and len(response_messages) > 1):
                raise Exception("Unexpected number of response messages for a " + TOOL_CALL_DESCRIPTION + ".")

            if number_of_calls == 0:
                break

            response_message = response_messages[0]

            logger.debug(response_message)

            result = OracleLLM.call_tool(tools, response_message)

            if result is None:
                break # this occurs if the tool call cannot be handled because the tool-call function is None.

            oracle_llm_content = OracleLLMContent(response_message, "string", ROLE_ASSISTANT)
            oracle_llm_content_list.append(oracle_llm_content)

            oracle_llm_content = OracleLLMContent("The function result of " + response_message + " is: " + result, "string", ROLE_SYSTEM)
            oracle_llm_content_list.append(oracle_llm_content)

        return response_messages
    

    def run_for_agent(self, *, oracle_llm_content_list: list[OracleLLMContent] = [], tools: list[OracleTool] = None) -> list[str]:
        user_message = ""

        if self._number_of_runs == 0:
            tool_descriptions = OracleLLM.get_tool_descriptions(tools)
            if tool_descriptions is not None:
                if len(user_message) > 0:
                    user_message += "\n"
                user_message += tool_descriptions

        for oracle_llm_content in reversed(oracle_llm_content_list):
            if oracle_llm_content.content_type == CONTENT_TYPE_STRING:
                if len(user_message) > 0:
                    user_message += "\n"
                user_message += oracle_llm_content.content_data
                break # kds - what if there are multiple new messages?  should multiple messages always be combined into one with new line delimiters?

        while True:
            logger.debug(user_message)

            chat_details = oci.generative_ai_agent_runtime.models.ChatDetails(
                session_id = self._session_id,
                user_message = user_message,
                should_stream = False
                )
            
            response = self._generative_ai_agent_runtime_client.chat(
                agent_endpoint_id = self._parameters.agent_endpoint_id,
                chat_details = chat_details
                )
            
            response_message = response.data.message.content.text

            logger.debug(response_message)
            
            response_messages = [response_message]

            if TOOL_CALL_PREFIX in response_message:
                if response_message.find(TOOL_CALL_PREFIX, 1) != -1:
                    raise Exception("Unexpectedly received a response message with an embedded " + TOOL_CALL_DESCRIPTION + ".")
                
                result = OracleLLM.call_tool(tools, response_message)

                if result is None:
                    break # this occurs if the tool call cannot be handled because the tool-call function is None.

                # kdsstart - adding the response_message on both lines may be unneeded and may confused the llm or the agent.
                # user_message = response_message + "\nThe function result of " + response_message + " is: " + result
                user_message = "The function result of " + response_message + " is: " + result
                # kdsend

                continue

            break

        return response_messages

    
    @staticmethod
    def get_tool_descriptions(tools):
        if tools is None or len(tools) == 0:
            return None
        
        tool_descriptions = "You are an assistant with access to the following functions:\n\n"

        for i in range(len(tools)):
            tool = tools[i]

            tool_descriptions += str(i + 1) + ". The function prototype is: " + tool.name + "("

            for j in range(len(tool.parameters)):
                parameter = tool.parameters[j]
                if j > 0:
                    tool_descriptions += ","
                tool_descriptions += parameter.name

            tool_descriptions += ") and the function description is: " + tool.description + "\n"

        tool_descriptions += "\nAlways indicate when you want to call a function by writing: \"" + TOOL_CALL_PREFIX + " function_name(parameters)\"\n"
        tool_descriptions += "Do not combine function calls and text responses in the same output: either only function calls or only text responses.\n"
        tool_descriptions += "For any string parameters, be sure to enclose each of them in double quotes."

        return tool_descriptions
    

    @staticmethod
    def call_tool(tools, tool_call):
        tool_call = tool_call[len(TOOL_CALL_PREFIX):].strip()
        original_tool_call = tool_call

        function_name, parameters = OracleLLM.parse_function_call(tool_call, TOOL_CALL_DESCRIPTION)

        found = False
        for tool in tools:
            if tool.name == function_name:
                found = True
                break

        if not found:
            raise Exception("Unknown function name: " + function_name + " in " + TOOL_CALL_DESCRIPTION + " response message: " + original_tool_call + ".")

        if tool.function is None:
            return None

        result = tool.function(* parameters)
        result = str(result)

        return result


    @staticmethod
    def parse_function_call(code_string, description):
        expression = ast.parse(code_string, mode = "eval").body

        if not isinstance(expression, ast.Call):
            raise Exception("Invalid " + description + ": " + code_string + ".")

        function_name = expression.func.id if isinstance(expression.func, ast.Name) else None
        if not function_name:
            raise Exception("Invalid " + description + ": " + code_string + ".")

        function_parameters = [ast.literal_eval(parameter) for parameter in expression.args]

        return function_name, function_parameters


class Parameters:
    """
    The parameters class. This class contains all parameter information for the Oracle LLM class.
    """

    secure: bool
    host: str
    port_number: int

    back_end: str

    compartment_id: str
    authentication_configuration_file_spec: str
    authentication_configuration_name: str
    model_type: str
    model_id: str
    model_name: str
    maximum_number_of_tokens: int
    temperature: float
    top_p: float
    top_k: int
    frequency_penalty: float
    presence_penalty: float
    seed: int

    agent_endpoint_id: str


@dataclass
class OracleLLMContent:
    """
    The Oracle LLM content class. This class contains all information related to one LLM content item.
    """

    content_data: Any
    content_type: str
    role: str


@dataclass
class OracleValue:
    """
    The Oracle value class. This class contains all information related to one value.
    """

    name: str
    description: str
    type: str


@dataclass
class OracleTool:
    """
    The Oracle tool class. This class contains all information related to one tool.
    """

    name: str
    description: str
    function: Callable[..., Any]
    parameters: list[OracleValue]
