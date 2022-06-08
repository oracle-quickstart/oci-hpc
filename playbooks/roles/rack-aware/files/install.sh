#!/bin/bash 
set -x 
python3 -m ensurepip
sudo python3 -m pip install --upgrade pip
python3 -m pip install pssh
python3 -m pip install parallel-ssh

