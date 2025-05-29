import docker, socket, random, time, threading
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, jsonify
from CTFd.plugins import register_plugin_assets_directory
from CTFd.utils.decorators import authed_only
from CTFd.utils.user import get_current_user

# Track timers and expiry for each user
user_containers = {}

def stop_and_remove_container(container_id):
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
        print(f"[ttyd_shell] Stopping and removing container {container_id}")
        container.stop()
        container.remove()
        # Mark the user's timer as expired
        for user_id, info in user_containers.items():
            if info.get("container_id") == container_id:
                info["expires_at"] = datetime.utcnow()  # Set expiry to now
                break
    except Exception as e:
        print(f"[ttyd_shell] Error during stopping: {e}")

def set_container_timer(user_id, container_id, lifetime_seconds):
    # Cancel previous timer if exists
    if user_id in user_containers and user_containers[user_id].get("timer"):
        user_containers[user_id]["timer"].cancel()
    expires_at = datetime.utcnow() + timedelta(seconds=lifetime_seconds)
    timer = threading.Timer(
        lifetime_seconds,
        stop_and_remove_container,
        args=[container_id]
    )
    timer.start()
    user_containers[user_id] = {
        "container_id": container_id,
        "timer": timer,
        "expires_at": expires_at
    }

MAX_SHELL_SECONDS = 7200  # 2 hours

def extend_container_timer(user_id, extra_seconds):
    if user_id not in user_containers:
        print("[ttyd_shell] No running container to extend.")
        return False, "No running container to extend."
    old = user_containers[user_id]
    old["timer"].cancel()
    now = datetime.utcnow()
    current_left = int((old["expires_at"] - now).total_seconds())
    if current_left >= MAX_SHELL_SECONDS:
        # Already at max
        print(f"[ttyd_shell] User {user_id} already at max shell time.")
        return False, "Maximum shell time is 2 hours."
    # Calculate new expiry, but cap at max
    new_left = min(current_left + extra_seconds, MAX_SHELL_SECONDS)
    new_expiry = now + timedelta(seconds=new_left)
    seconds_from_now = (new_expiry - now).total_seconds()
    if seconds_from_now <= 0:
        stop_and_remove_container(old["container_id"])
        return False, "Shell expired."
    timer = threading.Timer(
        seconds_from_now,
        stop_and_remove_container,
        args=[old["container_id"]]
    )
    timer.start()
    user_containers[user_id]["timer"] = timer
    user_containers[user_id]["expires_at"] = new_expiry
    print(f"[ttyd_shell] Extended container for user {user_id} until {new_expiry}")
    if new_left == MAX_SHELL_SECONDS:
        return True, "Shell time set to maximum (2 hours)."
    return True, "Shell time extended!"

def get_seconds_left(user_id):
    if user_id in user_containers:
        expires_at = user_containers[user_id]["expires_at"]
        left = int((expires_at - datetime.utcnow()).total_seconds())
        return max(0, left)
    return 0

def load(app):
    shell_plugin = Blueprint(
        'ttyd_shell', __name__,
        template_folder='templates',
        static_folder='assets'
    )

    @shell_plugin.route('/shell')
    @authed_only
    def shell():
        user = get_current_user()
        port = create_shell_container(user.name)
        return render_template("shell.html", port=port)

    @shell_plugin.route('/extend_shell')
    @authed_only
    def extend_shell():
        user = get_current_user()
        success, msg = extend_container_timer(user.name, 3600)  # 1 hour
        if success:
            return msg, 200
        else:
            return msg, 400

    @shell_plugin.route('/shell_time_left')
    @authed_only
    def shell_time_left():
        user = get_current_user()
        seconds_left = get_seconds_left(user.name)
        return jsonify({"seconds_left": seconds_left})

    app.register_blueprint(shell_plugin)

def assign_port(start=9000, end=10000):
    client = docker.from_env()
    used_ports = set()
    for c in client.containers.list():
        ports = c.attrs['HostConfig'].get('PortBindings', {})
        if '7681/tcp' in ports:
            for binding in ports['7681/tcp']:
                try:
                    used_ports.add(int(binding['HostPort']))
                except (KeyError, ValueError, TypeError):
                    continue
    candidate_ports = list(range(start, end))
    random.shuffle(candidate_ports)
    for port in candidate_ports:
        if port in used_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            if sock.connect_ex(('localhost', port)) != 0:
                return port
    raise RuntimeError("No available ports found in range.")

def create_shell_container(username):
    client = docker.from_env()
    container_name = f"ttyd_shell_{username}"
    try:
        container = client.containers.get(container_name)
        if container.status != 'running':
            container.remove(force=True)
            raise docker.errors.NotFound("Container existed but not running")
        else:
            print(f"[DEBUG] Container already running for {username}")
            # Reset timer if container is running
            set_container_timer(username, container.id, get_seconds_left(username) or 3600)  # 1 hour
            return int(container.attrs['HostConfig']['PortBindings']['7681/tcp'][0]['HostPort'])
    except docker.errors.NotFound:
        pass
    except Exception as e:
        print(f"[ERROR] Unexpected error when getting container: {e}")

    host_port = assign_port()
    print(f"[DEBUG] Creating new container for {username} on port {host_port}")

    try:
        container = client.containers.run(
            image="ttyd_shell",
            name=container_name,
            detach=True,
            ports={'7681/tcp': host_port},
            environment={"USERNAME": username},
            cap_add=["NET_ADMIN"],
            tty=True,
            auto_remove=True,
            labels={},
            mem_limit="256m",
            nano_cpus=200_000_000
            #user="1000:1000"
        )
        print(f"[DEBUG] Container created: {container.id}")
        set_container_timer(username, container.id, 3600)  # 1 hour
        return host_port
    except Exception as e:
        print(f"[ERROR] Failed to create container for {username}: {e}")
        import traceback
        traceback.print_exc()
        raise

