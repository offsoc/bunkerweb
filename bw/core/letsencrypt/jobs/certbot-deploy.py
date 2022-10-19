#!/usr/bin/python3

from asyncio import run
from io import BytesIO
from os import environ, getenv
from os.path import exists
from subprocess import DEVNULL, STDOUT
from sys import exit as sys_exit, path as sys_path
from tarfile import open as tar_open
from traceback import format_exc

sys_path.append("/opt/bunkerweb/deps/python")
sys_path.append("/opt/bunkerweb/utils")
sys_path.append("/opt/bunkerweb/api")

from logger import setup_logger
from API import API

logger = setup_logger("Lets-encrypt", getenv("LOG_LEVEL", "INFO"))
status = 0

try:
    # Get env vars
    bw_integration = None
    if getenv("KUBERNETES_MODE") == "yes":
        bw_integration = "Swarm"
    elif getenv("SWARM_MODE") == "yes":
        bw_integration = "Kubernetes"
    elif getenv("AUTOCONF_MODE") == "yes":
        bw_integration = "Autoconf"
    elif exists("/opt/bunkerweb/INTEGRATION"):
        with open("/opt/bunkerweb/INTEGRATION", "r") as f:
            bw_integration = f.read().strip()
    token = getenv("CERTBOT_TOKEN")

    # Cluster case
    if bw_integration in ("Swarm", "Kubernetes", "Autoconf"):
        # Create tarball of /data/cache/letsencrypt
        tgz = BytesIO()
        with tar_open(mode="w:gz", fileobj=tgz) as tf:
            tf.add("/data/cache/letsencrypt", arcname=".")
        tgz.seek(0, 0)
        files = {"archive.tar.gz": tgz}

        for variable, value in environ.items():
            if not variable.startswith("CLUSTER_INSTANCE_"):
                continue
            endpoint = value.split(" ")[0]
            host = value.split(" ")[1]
            api = API(endpoint, host=host)
            sent, err, status, resp = api.request(
                "POST", "/lets-encrypt/certificates", files=files
            )
            if not sent:
                status = 1
                logger.error(
                    f"Can't send API request to {api.get_endpoint()}/lets-encrypt/certificates : {err}"
                )
            else:
                if status != 200:
                    status = 1
                    logger.error(
                        f"Error while sending API request to {api.get_endpoint()}/lets-encrypt/certificates : status = {resp['status']}, msg = {resp['msg']}"
                    )
                else:
                    logger.info(
                        f"Successfully sent API request to {api.get_endpoint()}/lets-encrypt/certificates",
                    )
                    sent, err, status, resp = api.request("POST", "/reload")
                    if not sent:
                        status = 1
                        logger.error(
                            f"Can't send API request to {api.get_endpoint()}/reload : {err}"
                        )
                    else:
                        if status != 200:
                            status = 1
                            logger.error(
                                f"Error while sending API request to {api.get_endpoint()}/reload : status = {resp['status']}, msg = {resp['msg']}"
                            )
                        else:
                            logger.info(
                                f"Successfully sent API request to {api.get_endpoint()}/reload"
                            )

    # Docker or Linux case
    elif bw_integration == "Docker":
        api = API(f"{getenv('BW_API_URL')}:5000")
        sent, err, status, resp = api.request("POST", "/reload")
        if not sent:
            status = 1
            logger.error(
                f"Can't send API request to {api.get_endpoint()}/reload : {err}"
            )
        else:
            if status != 200:
                status = 1
                logger.error(
                    f"Error while sending API request to {api.get_endpoint()}/reload : status = {resp['status']}, msg = {resp['msg']}"
                )
            else:
                logger.info(
                    f"Successfully sent API request to {api.get_endpoint()}/reload"
                )
    elif bw_integration == "Linux":
        cmd = "/usr/sbin/nginx -s reload"
        proc = run(cmd.split(" "), stdin=DEVNULL, stderr=STDOUT)
        if proc.returncode != 0:
            status = 1
            logger.error("Error while reloading nginx")
        else:
            logger.info("Successfully reloaded nginx")

except:
    status = 1
    logger.error(f"Exception while running certbot-deploy.py :\n{format_exc()}")

sys_exit(status)