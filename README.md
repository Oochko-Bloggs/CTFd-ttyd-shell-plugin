# CTFd-ttyd-shell-plugin
## Configuration guide

 1. **Clone this repository** into the `CTFd/plugins` directory, and mount the plugin path into your `docker-compose.yml` file if you plan to continue development:
	```
	- ./CTFd/plugins/ttyd_shell:/opt/CTFd/CTFd/plugins/ttyd_shell
	```
	
 2. **Mount the Docker socket** into the CTFd container by adding the following line under the `ctfd` service's `volumes` section in your `docker-compose.yml`:
	```
	- /var/run/docker.sock:/var/run/docker.sock
	```
	This allows the plugin to run and manage Docker containers. However, be aware that this introduces a security risk — do **not** use `--privileged` mode, and make sure to implement proper security precautions.
 3. Build the shell image manually with :
	```
	docker build -t ttyd_shell . 
	```
	Or, add the following service to your `docker-compose.yml` to build it automatically:
	```
	  ttyd_shell:
	    build:
	      context: ./CTFd/plugins/ttyd_shell
	    image: ttyd_shell
	```
	this automaticaly build the shell image when **docker-compose up --build** command runs.
	
 4. Add the shell page from ctfd admin panel:
		
	 -   Set any name for the **{Page Name}**
    
	-   Set the **Route** to `/shell`
----

