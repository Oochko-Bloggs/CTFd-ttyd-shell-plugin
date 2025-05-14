import docker
import re
import time

client = docker.from_env()

def list_running_containers():
    containers = client.containers.list()
    pattern = re.compile(r"^ttyd_shell.*")

    for container in containers:
        if pattern.match(container.name):
            container_id = container.short_id
            name = container.name
            ports = container.attrs['NetworkSettings']['Ports']

            print(f"Name: {name}")
            print(f"Container ID: {container_id}")
            print("Port Bindings:")
            if ports:
                for port, bindings in ports.items():
                    print(f"  {port} -> {bindings}")
            else:
                print("  No port bindings.")
            print(f"Status {container.status}")
            print("-" * 40)

def cleanup_expired_containers():
    containers = client.containers.list(all=True)
    pattern = re.compile(r"^ttyd_shell.*")
    now = int(__import__('time').time())
    for container in containers:
        if pattern.match(container.name):
            expiry = container.labels.get('expiry')
            if expiry:
                try:
                    expiry = int(expiry)
                    if expiry < now:
                        print(f"[CLEANUP] Removing expired container: {container.name}")
                        container.remove(force=True)
                except Exception as e:
                    print(f"[ERROR] Could not parse expiry for {container.name}: {e}")

def main_loop():
    while True:
        cleanup_expired_containers()
        time.sleep(60)  # Sleep for 1 minute

if __name__ == "__main__":
    main_loop()