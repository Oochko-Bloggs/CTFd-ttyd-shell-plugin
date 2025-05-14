#!/bin/bash

USERNAME="${USERNAME:-ctfuser}"

# Create user if needed
if ! id "$USERNAME" &>/dev/null; then
    useradd -m "$USERNAME"
    echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
fi

# Load vcan module and set up vcan0
modprobe vcan
ip link add dev vcan0 type vcan || true
ip link set up vcan0

# Optional: disable eth0 if needed
#if ip link show eth0 &>/dev/null; then
#    ip link set dev eth0 down
#fi

# Start ttyd server as created user
exec su - "$USERNAME" -c "ttyd --writable --interface 0.0.0.0 -p 7681 /bin/bash"