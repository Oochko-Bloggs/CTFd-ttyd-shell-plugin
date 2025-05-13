FROM ubuntu:22.04

# Create ctfuser
RUN useradd -m ctfuser && apt-get update && \
    apt-get install -y curl ca-certificates bash && \
    curl -L https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 -o /usr/local/bin/ttyd && \
    chmod +x /usr/local/bin/ttyd

USER ctfuser
WORKDIR /home/ctfuser

EXPOSE 7681

CMD ["ttyd", "--writable", "-p", "7681", "/bin/bash"]