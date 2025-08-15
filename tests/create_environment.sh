#!/bin/zsh

brew install python@3.11

rm -rf myenv
python3.11 -m venv myenv

source myenv/bin/activate

pip install --upgrade pip

pip install torch
pip install python-dotenv
pip install fastmcp

pip install pdoc

pip install "livekit-agents[deepgram,openai,cartesia,silero,turn-detector]==1.0.22"
pip install "livekit-plugins-noise-cancellation==0.2.5"

pip install "oci-ai-speech-realtime==2.1.0"

python3.11 main.py download-files

deactivate
