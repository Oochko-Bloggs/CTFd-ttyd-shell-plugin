FROM ubuntu:22.04

# Install dependencies, net-tools, kmod, iproute2, and ttyd
RUN apt-get update && \
    apt-get install -y curl ca-certificates bash sudo \
    iproute2 net-tools kmod && \
    curl -L https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 -o /usr/local/bin/ttyd && \
    chmod +x /usr/local/bin/ttyd

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 7681

ENTRYPOINT ["/entrypoint.sh"]