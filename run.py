import os
import re
import sys
import time
import logging
import threading
import signal
import docker
import socket
import dns.resolver
from requests.exceptions import ConnectionError


KUBELET_INTERVAL = int(os.environ.get('KUBELET_INTERVAL', 120))
KUBELET_CHECK_STRING = os.environ.get('KUBELET_CHECK_STRING', "use of closed network connection")
KUBELET_STRING_THRESHOLD = int(os.environ.get('KUBELET_STRING_THRESHOLD', 3))
KUBELET_CHECK_SEPARATOR = os.environ.get('KUBELET_CHECK_SEPARATOR', ",")
NAME_SERVERS = os.environ.get('NAME_SERVERS')
LOG_DEBUG = True if str(os.environ.get('LOG_DEBUG')).lower() == "true" else False
RUNNING = True
LOGGERS = {}
THREADS = []


class StopWork(Exception):
    pass


def get_hostname(string):
    """
    If the input string is an IP, then perform a DNS reverse lookup to get the name
    :param string: IP address or hostname to lookup
    :return: Hostname that the IP resolves to, or the original string if not an IP
    """
    hostname = string
    try:
        socket.inet_aton(str(string))
    except OSError:
        return str(hostname)
    nameservers = []
    for server in NAME_SERVERS.split(','):
        resp1 =  dns.resolver.resolve(server)
        for answer in resp1:
            nameservers.append(answer.address)
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = nameservers
    dns.resolver.default_resolver = resolver
    try:
        resp2 = dns.resolver.resolve_address(string)
        for host in resp2:
            hostname = str(host.target).rstrip(".")
    except dns.resolver.NXDOMAIN:
        pass
    return hostname


def get_logger(logger_id='BASELOGGER', verbose=False):
    if logger_id in LOGGERS:
        return LOGGERS[logger_id]
    else:
        logger = logging.getLogger(logger_id)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        if verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        LOGGERS[logger_id] = logger
        return logger


def find_container_by_name(client, log, name):
    for _c in client.containers.list():
        if _c.name == name:
            return _c
    log.error("[find_container_by_name: %s] Did not find container named '%s'", MY_NODE_NAME, name)
    return None


def sleep(num):
    """ Custom sleep that checks to see if we should still be running """
    for _ in range(num):
        if RUNNING:
            time.sleep(1)
        else:
            raise StopWork


def check_kubelet_connection(client, log):
    patterns = []
    for string in KUBELET_CHECK_STRING.split(KUBELET_CHECK_SEPARATOR):
        patterns.append(re.compile(string))
    while True:
        log.debug("[check_kubelet_connection: %s] Starting main while loop", MY_NODE_NAME)
        try:
            kubelet = find_container_by_name(client, log, "kubelet")
            if kubelet:
                alive = True
                while alive:
                    num = 0
                    log.debug("[check_kubelet_connection: %s] Starting alive while loop", MY_NODE_NAME)
                    logs = kubelet.logs(since=(int(time.time()) - KUBELET_INTERVAL)).decode("utf-8")
                    need_slap = False
                    for pattern in patterns:
                        num = len(pattern.findall(logs))
                        if num:
                            log.warning("[check_kubelet_connection: %s] Found string '%s' %s times in kubelet logs",
                                        MY_NODE_NAME, pattern.pattern, num)
                            if num >= KUBELET_STRING_THRESHOLD:
                                need_slap = True
                        else:
                            log.info("[check_kubelet_connection: %s] kubelet connection is ok", MY_NODE_NAME)
                    if need_slap:
                        log.warning("[check_kubelet_connection: %s] Restarting kubelet due to lost connection",
                                    MY_NODE_NAME)
                        kubelet.restart()
                        alive = False
                    log.debug("[check_kubelet_connection: %s] Sleeping %s seconds", MY_NODE_NAME, KUBELET_INTERVAL)
                    sleep(KUBELET_INTERVAL)
                log.debug("[check_kubelet_connection: %s] End of alive while loop", MY_NODE_NAME)
            else:
                log.info("[check_kubelet_connection: %s] Sleeping while waiting for kubelet container to start",
                         MY_NODE_NAME)
                sleep(10)
        except StopWork:
            log.debug("[check_kubelet_connection: %s] Stopping...", MY_NODE_NAME)
            return
        except docker.errors.NotFound:
            log.error("[check_kubelet_connection: %s] Docker didn't find the container, retrying", MY_NODE_NAME)
            sleep(5)
        except ConnectionError:
            log.error("Got a ConnectionError while communicating with Docker, returning")
            return
        except Exception as e:
            log.exception("Got exception, returning")
            return
        log.debug("[check_kubelet_connection: %s] End of main while loop", MY_NODE_NAME)


def graceful_exit(signum, frame):
    global RUNNING
    print(f"[graceful_exit:{MY_NODE_NAME}] Received exit signal {signum}")
    RUNNING = False
    for _t in THREADS:
        _t.join()
    exit(signum)


MY_NODE_NAME = get_hostname(os.environ.get('MY_NODE_NAME'))


def main():
    log = get_logger('slapper', LOG_DEBUG)
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)
    try:
        client = docker.from_env()
        kubelet_thread = threading.Thread(target=check_kubelet_connection, args=(client, log))
        THREADS.append(kubelet_thread)
        for _thread in THREADS:
            _thread.start()
        sleep(5)
        while True:
            for _thread in THREADS:
                if not _thread.is_alive():
                    log.info("[main: %s] Thread %s is no longer running, exiting", MY_NODE_NAME, _thread.name)
                    graceful_exit(1, None)
            sleep(60)
    except Exception:
        log.exception("[main: %s] Exception in main()", MY_NODE_NAME)
        sleep(10)


if __name__ == "__main__":
    main()
