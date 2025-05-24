import docker, socket, random, time
from flask import Blueprint, render_template, redirect, url_for
from CTFd.plugins import register_plugin_assets_directory
from CTFd.utils.decorators import authed_only
from CTFd.utils.user import get_current_user
from CTFd.utils.security.passwords import check_password

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
        success = extend_container_expiry(user.name, hours=1)
        if success:
            return "Shell time extended by 1 hour!", 200
        else:
            return "Failed to extend shell time.", 500

    @shell_plugin.route('/shell_time_left')
    @authed_only
    def shell_time_left():
        user = get_current_user()
        client = docker.from_env()
        container_name = f"ttyd_shell_{user.name}"
        try:
            container = client.containers.get(container_name)
            expiry = container.labels.get('expiry')
            if expiry:
                expiry = int(expiry)
                now = int(time.time())
                seconds_left = max(0, expiry - now)
                return {"seconds_left": seconds_left}
        except Exception:
            pass
        return {"seconds_left": 0}

    app.register_blueprint(shell_plugin)

def assign_port(start=9000, end=10000):
    client = docker.from_env()
    used_ports = set()

    # Collect all ports already used by Docker containers
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

    # Find a port that's both free on the host AND not already mapped in Docker
    for port in candidate_ports:
        if port in used_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            if sock.connect_ex(('localhost', port)) != 0:
                return port

    raise RuntimeError("No available ports found in range.")

def get_container_expiry(container):
    # Returns expiry timestamp (int) or None
    expiry = container.labels.get('expiry')
    if expiry:
        try:
            return int(expiry)
        except Exception:
            return None
    return None

def set_container_expiry(container, expiry_ts):
    # Docker doesn't allow updating labels directly, so we recreate with new label
    # Not used for extension, just for initial creation
    pass  # Placeholder for future use if needed

def extend_container_expiry(username, hours=1):
    client = docker.from_env()
    container_name = f"ttyd_shell_{username}"
    try:
        container = client.containers.get(container_name)
        expiry = get_container_expiry(container)
        now = int(time.time())
        if not expiry or expiry < now:
            expiry = now + hours * 3600
        else:
            expiry += hours * 3600
        # Docker doesn't support updating labels in place, so workaround: commit & recreate
        container.commit(repository=container.image.tags[0], changes=None)
        container.remove(force=True)
        new_container = client.containers.run(
            image=container.image.tags[0],
            name=container_name,
            detach=True,
            ports=container.attrs['HostConfig']['PortBindings'],
            environment=container.attrs['Config']['Env'],
            cap_add=container.attrs['HostConfig'].get('CapAdd', []),
            tty=True,
            auto_remove=True,
            labels={**container.labels, 'expiry': str(expiry)}
        )
        return True
    except Exception:
        return False

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
            return int(container.attrs['HostConfig']['PortBindings']['7681/tcp'][0]['HostPort'])
    except docker.errors.NotFound:
        pass

    host_port = assign_port()
    expiry = int(time.time()) + 3600  # 1 hour from now
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
        labels={"expiry": str(expiry)}
    )
    return host_port
