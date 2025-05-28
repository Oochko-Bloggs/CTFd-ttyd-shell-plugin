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

def extend_container_timer(user_id, extra_seconds):
    if user_id not in user_containers:
        print("[ttyd_shell] No running container to extend.")
        return False
    old = user_containers[user_id]
    old["timer"].cancel()
    new_expiry = old["expires_at"] + timedelta(seconds=extra_seconds)
    seconds_from_now = (new_expiry - datetime.utcnow()).total_seconds()
    if seconds_from_now <= 0:
        stop_and_remove_container(old["container_id"])
        return False
    timer = threading.Timer(
        seconds_from_now,
        stop_and_remove_container,
        args=[old["container_id"]]
    )
    timer.start()
    user_containers[user_id]["timer"] = timer
    user_containers[user_id]["expires_at"] = new_expiry
    print(f"[ttyd_shell] Extended container for user {user_id} until {new_expiry}")
    return True

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
        success = extend_container_timer(user.name, 60)
        if success:
            return "Shell time extended by 1 hour!", 200
        else:
            return "Failed to extend shell time.", 500

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
            set_container_timer(username, container.id, get_seconds_left(username) or 60)
            return int(container.attrs['HostConfig']['PortBindings']['7681/tcp'][0]['HostPort'])
    except docker.errors.NotFound:
        pass

    host_port = assign_port()
    print(f"[DEBUG] Creating new container for {username} on port {host_port}")
    container = client.containers.run(
        image="ttyd_shell",
        name=container_name,
        detach=True,
        ports={'7681/tcp': host_port},
        environment={"USERNAME": username},
        cap_add=["NET_ADMIN"],
        tty=True,
        auto_remove=True,
        labels={}
    )
    set_container_timer(username, container.id, 60)  # 1 minute for debugging
    return host_port
