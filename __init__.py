import docker, socket
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

    # Find a port that's both free on the host AND not already mapped in Docker
    for port in range(start, end):
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
        auto_remove=True
    )
    return host_port
