"""The box: its key, its address, and what is allowed to reach it."""

# PEP 563: annotations stay strings, so `list[str] | None` and friends do not
# need Python 3.10 at runtime -- whatever python3 built the venv will do.
from __future__ import annotations

import pathlib
from typing import NamedTuple

import pulumi_aws as aws


class Box(NamedTuple):
    instance: aws.lightsail.Instance
    ip: aws.lightsail.StaticIp


def provision(
    *,
    availability_zone: str,
    bundle_id: str,
    ssh_public_key: str,
    admin_ssh_cidr: str,
    tags: dict,
) -> Box:
    key_pair = aws.lightsail.KeyPair(
        "proline-ssh", name="proline-ssh", public_key=ssh_public_key, tags=tags
    )

    instance = aws.lightsail.Instance(
        "proline-prod",
        name="proline-prod",
        availability_zone=availability_zone,
        # OS only. The Bitnami and "Docker" blueprints arrive with their own
        # Apache or nginx already bound to port 80 -- which is where OUR nginx
        # container has to publish, and the collision is a container that will
        # not start with no obvious reason why.
        blueprint_id="ubuntu_24_04",
        bundle_id=bundle_id,
        key_pair_name=key_pair.name,
        # IPv4 only, to match the DNS plan. Dualstack would hand out an IPv6
        # address that nothing resolves to, which looks like a broken site to
        # exactly the people whose networks prefer IPv6.
        ip_address_type="ipv4",
        user_data=pathlib.Path(__file__).with_name("user-data.sh").read_text(),
        # Whole-disk snapshots, ~$0.60/month, and the ONLY recovery point this
        # deployment has. It covers everything on the disk: the pgdata volume
        # with every lead in it, the certbot_conf volume holding the certificate
        # and its private key, and the .env and db_password files that exist
        # nowhere else. One per day, and a restore creates a NEW instance -- so
        # recovery also means re-attaching the static IP below.
        add_on=aws.lightsail.InstanceAddOnArgs(
            type="AutoSnapshot",
            snapshot_time="07:00",  # UTC; 03:00 in Montreal
            status="Enabled",
        ),
        tags=tags,
    )

    # Without this the address changes every time the instance stops, and the
    # DNS records below it silently point at nothing. Free while attached.
    ip = aws.lightsail.StaticIp("proline-ip", name="proline-ip")

    aws.lightsail.StaticIpAttachment(
        "proline-ip-attachment", static_ip_name=ip.name, instance_name=instance.name
    )

    # This REPLACES the instance's whole port rule set rather than adding to it,
    # which is the reason to declare it here: a new Lightsail instance comes with
    # defaults (SSH always, and 80/443 on the web-server blueprints but not on
    # OS-only), and rather than reasoning about which ones this image happened to
    # get, these three rules become the entire set. Anything else that was open is
    # closed by the first `pulumi up`.
    aws.lightsail.InstancePublicPorts(
        "proline-ports",
        instance_name=instance.name,
        port_infos=[
            aws.lightsail.InstancePublicPortsPortInfoArgs(
                protocol="tcp", from_port=80, to_port=80, cidrs=["0.0.0.0/0"]
            ),
            aws.lightsail.InstancePublicPortsPortInfoArgs(
                protocol="tcp", from_port=443, to_port=443, cidrs=["0.0.0.0/0"]
            ),
            aws.lightsail.InstancePublicPortsPortInfoArgs(
                protocol="tcp", from_port=22, to_port=22, cidrs=[admin_ssh_cidr]
            ),
        ],
    )

    return Box(instance=instance, ip=ip)
