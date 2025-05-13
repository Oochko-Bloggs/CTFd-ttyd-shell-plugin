#!/bin/bash

sudo modprobe vcan

sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

if ip link show eth0 > /dev/null 2>&1; then
  sudo ip link set dev eth0 down
fi

# Start ttyd
exec ttyd --writable -p 7681 /bin/bash
