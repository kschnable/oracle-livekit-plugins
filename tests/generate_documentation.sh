#!/bin/zsh

source myenv/bin/activate

rm -rf ../docs
pdoc ../src/oracle/livekit/plugins --output-dir ../docs

deactivate
