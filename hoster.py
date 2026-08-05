#!/usr/bin/python3
import docker
import argparse
import shutil
import signal
import time
import sys
import os

label_name = "hoster.domains"
enclosing_pattern = "#-----------Docker-Hoster-Domains----------\n"
hosts_path = "/tmp/hosts"
hosts = {}

def signal_handler(signal, frame):
    global hosts
    hosts = {}
    update_hosts_file()
    sys.exit(0)

def main():
    # register the exit signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    args = parse_args()
    global hosts_path
    hosts_path = args.file

    dockerClient = docker.APIClient(base_url='unix://%s' % args.socket)
    events = dockerClient.events(decode=True)
    #get running containers
    for c in dockerClient.containers(quiet=True, all=False):
        container_id = c["Id"]
        container = get_container_data(dockerClient, container_id)
        hosts[container_id] = container

    update_hosts_file()

    #listen for events to keep the hosts file updated
    for e in events:
        if handle_event(dockerClient, e):
            update_hosts_file()


def get_event_action(e):
    #the event verb moved between API versions: old daemons send "status",
    #modern ones send "Action" and omit "status" altogether. Some actions are
    #qualified, e.g. "exec_start: ls -l" or "health_status: healthy", and only
    #the verb in front of the colon is meaningful here.
    action = e.get("status") or e.get("Action") or ""
    return action.split(":", 1)[0].strip()


def get_event_container_id(e):
    #old daemons send a top-level "id", modern ones only "Actor"."ID"
    return e.get("id") or (e.get("Actor") or {}).get("ID") or ""


def handle_event(dockerClient, e):
    #apply a single docker event to the hosts table,
    #returning True when the table actually changed
    if e.get("Type") != "container":
        return False

    action = get_event_action(e)
    container_id = get_event_container_id(e)
    if not container_id:
        return False

    if action == "start":
        hosts[container_id] = get_container_data(dockerClient, container_id)
        return True

    if action in ("stop", "die", "destroy"):
        if container_id in hosts:
            hosts.pop(container_id)
            return True

    return False


def get_container_data(dockerClient, container_id):
    #extract all the info with the docker api
    info = dockerClient.inspect_container(container_id)
    container_hostname = info["Config"]["Hostname"]
    container_name = info["Name"].strip("/")
    #the top-level IPAddress is absent on modern daemons; it survives here only
    #to keep working against older ones
    container_ip = info["NetworkSettings"].get("IPAddress", "")
    if not container_ip:
        network_mode = (info.get("HostConfig") or {}).get("NetworkMode") or ""
        if network_mode.startswith("container:"):
            pid = network_mode[len("container:"):]
            info = dockerClient.inspect_container(pid)
            container_ip = info["NetworkSettings"].get("IPAddress", "")
        elif network_mode == "host":
            container_ip = "127.0.0.1"

    if info["Config"].get("Domainname"):
        container_hostname = container_hostname + "." + info["Config"]["Domainname"]

    result = []
    seen_ips = set()

    networks = info["NetworkSettings"].get("Networks") or {}
    for values in networks.values():

        network_ip = values.get("IPAddress", "")
        #the default bridge network carries no Aliases, and modern daemons no
        #longer expose the top-level IPAddress to fall back on, so a network
        #without aliases must still map the container's own names
        aliases = values.get("Aliases") or []
        if not network_ip and not aliases:
            continue

        if network_ip:
            if network_ip in seen_ips:
                continue
            seen_ips.add(network_ip)

        result.append({
                "ip": network_ip,
                "name": container_name,
                "domains": set(aliases + [container_name, container_hostname])
            })

    if container_ip and container_ip not in seen_ips:
        result.append({"ip": container_ip, "name": container_name, "domains": [container_name, container_hostname ]})

    return result


def update_hosts_file():
    if len(hosts)==0:
        print("Removing all hosts before exit...")
    else:
        print("Updating hosts file with:")

    for id,addresses in hosts.items():
        for addr in addresses:
            print("ip: %s domains: %s" % (addr["ip"], addr["domains"]))

    #read all the lines of thge original file
    lines = []
    with open(hosts_path,"r+") as hosts_file:
        lines = hosts_file.readlines()

    #remove all the lines after the known pattern
    for i,line in enumerate(lines):
        if line==enclosing_pattern:
            lines = lines[:i]
            break;

    #remove all the trailing newlines on the line list
    if lines:
        while lines[-1].strip()=="": lines.pop()

    #append all the domain lines
    if len(hosts)>0:
        lines.append("\n\n"+enclosing_pattern)
        
        for id, addresses in hosts.items():
            for addr in addresses:
                lines.append("%s    %s\n"%(addr["ip"],"   ".join(addr["domains"])))
        
        lines.append("#-----Do-not-add-hosts-after-this-line-----\n\n")

    #write it on the auxiliar file
    aux_file_path = hosts_path+".aux"
    with open(aux_file_path,"w") as aux_hosts:
        aux_hosts.writelines(lines)

    #replace etc/hosts with aux file, making it atomic
    shutil.move(aux_file_path, hosts_path)


def parse_args():
    parser = argparse.ArgumentParser(description='Synchronize running docker container IPs with host /etc/hosts file.')
    parser.add_argument('socket', type=str, nargs="?", default="tmp/docker.sock", help='The docker socket to listen for docker events.')
    parser.add_argument('file', type=str, nargs="?", default="/tmp/hosts", help='The /etc/hosts file to sync the containers with.')
    return parser.parse_args()

if __name__ == '__main__':
    main()

