#!/bin/bash

# Only run setup if vcan0 not already created
if ! ip link show vcan0 > /dev/null 2>&1; then
    sudo modprobe vcan
    sudo ip link add dev vcan0 type vcan
    sudo ip link set up vcan0
fi

# Optional: disable eth0 if exists
if ip link show eth0 > /dev/null 2>&1; then
    sudo ip link set dev eth0 down
fi

# Start ttyd shell
exec ttyd --writable -p 7681 /bin/bash