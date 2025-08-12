This repo contains three Oracle LiveKit plug-ins:
1. The STT (speech to text) plug-in.  ./src/oracle/livekit/plugins/oracle_stt_livekit_plugin.py
2. The LLM (large language model) plug-in.  ./src/oracle/livekit/plugins/oracle_llm_livekit_plugin.py
3. The TTS (text to speech) plug-in.  ./src/oracle/livekit/plugins/oracle_tts_livekit_plugin.py

For testing these three plug-ins:
1. Edit tests/main.py and modify some of the plug-in parameters such as host and compartment_id
   accordingly for your Oracle access / configuration.
2. Use a command shell and enter the tests directory.
3. Execute ./create_environment.sh to create the test Python environment.
4. Execute ./run_mcp_server.sh to run the test MCP server.
5. Execute ./run_livekit.sh to test the three plug-ins in a local LiveKit environment.
6. Execute ./destroy_environment.sh to destroy the test Python environment.

The tests/main.py can be modified to change which plug-ins to test at any given time. Currently the code
will test all three but it is easy to revert to the default plug-ins for STT, LLM, and/or TTS (Deepgram,
OpenAI, and/or Cartesia respectively).

There are both local test tools (functions in main.py) and MCP test tools (functions in mcp_server.py)
that will be called appropriately when necessary. Some example requests that would use these specific
tools are:
1. What is the weather in Dallas?
2. What is my BMI if my weight is 150 pounds and my height is 70 inches?
3. Who has employee ID 17?
4. What is 7 factorial?
