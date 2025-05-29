import docker
import re
import time
import redis
from datetime import datetime, timedelta

client = docker.from_env()
r = redis.Redis(host='localhost', port=6379, db=0)  # Adjust if needed

CONTAINER_PREFIX = "ttyd_shell"
IDLE_TIMEOUT = 30 * 60  # 30 minutes in seconds

def list_running_containers():
    containers = client.containers.list()
    pattern = re.compile(rf"^{CONTAINER_PREFIX}.*")
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

def mark_expired(container_name):
    r.hset(f"shell_status:{container_name}", "expired", 1)
    r.hset(f"shell_status:{container_name}", "expires_at", int(time.time()))

def cleanup_expired_containers():
    containers = client.containers.list(all=True)
    pattern = re.compile(rf"^{CONTAINER_PREFIX}.*")
    now = int(time.time())
    for container in containers:
        if pattern.match(container.name):
            # Check for expiry in Redis
            status_key = f"shell_status:{container.name}"
            expires_at = r.hget(status_key, "expires_at")
            if expires_at and int(expires_at) < now:
                print(f"[CLEANUP] Removing expired container: {container.name}")
                container.remove(force=True)
                mark_expired(container.name)

def stop_idle_containers():
    containers = client.containers.list()
    pattern = re.compile(rf"^{CONTAINER_PREFIX}.*")
    now = int(time.time())
    for container in containers:
        if pattern.match(container.name):
            status_key = f"shell_status:{container.name}"
            last_active = r.hget(status_key, "last_active")
            if last_active:
                last_active = int(last_active)
                if now - last_active > IDLE_TIMEOUT:
                    print(f"[IDLE] Stopping idle container: {container.name}")
                    container.stop()
                    mark_expired(container.name)
            else:
                # If no activity info, set now as last_active
                r.hset(status_key, "last_active", now)

def get_container_cpu_percent(container):
    try:
        stats = container.stats(stream=False)
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
        if system_delta > 0 and cpu_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * len(stats["cpu_stats"]["cpu_usage"]["percpu_usage"]) * 100.0
            return cpu_percent
    except Exception as e:
        print(f"[ERROR] Could not get CPU usage for {container.name}: {e}")
    return 0.0

# Track idle time in memory for debug (reset on restart)
container_idle = {}

def stop_cpu_idle_containers(idle_seconds=60, cpu_threshold=0.5):
    containers = client.containers.list()
    pattern = re.compile(rf"^{CONTAINER_PREFIX}.*")
    now = time.time()
    for container in containers:
        if pattern.match(container.name):
            cpu = get_container_cpu_percent(container)
            if cpu < cpu_threshold:
                idle_info = container_idle.get(container.name, {"since": now, "last_cpu": cpu})
                if now - idle_info["since"] >= idle_seconds:
                    print(f"[IDLE-CPU] Stopping container {container.name} due to low CPU usage ({cpu:.2f}%)")
                    container.stop()
                    mark_expired(container.name)
                    container_idle.pop(container.name, None)
                else:
                    container_idle[container.name] = {"since": idle_info["since"], "last_cpu": cpu}
            else:
                # Reset idle timer if CPU usage is above threshold
                container_idle[container.name] = {"since": now, "last_cpu": cpu}

def main_loop():
    while True:
        cleanup_expired_containers()
        stop_idle_containers()
        stop_cpu_idle_containers(idle_seconds=60, cpu_threshold=0.5)  # 1 min for debug
        time.sleep(10)  # Check more frequently for debug

if __name__ == "__main__":
    main_loop()