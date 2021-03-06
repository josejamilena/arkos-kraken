import json

from flask import Blueprint, jsonify, request

from kraken import auth
from arkos import config
from arkos.system import sysconfig, systemtime

backend = Blueprint("config", __name__)


@backend.route('/config', methods=["GET", "PUT"])
@auth.required()
def arkos_config():
    if request.method == "PUT":
        config.config = json.loads(request.data)["config"]
        config.save()
    return jsonify(config=config.config)

@backend.route('/config/hostname', methods=["GET", "PUT"])
@auth.required()
def hostname():
    if request.method == "PUT":
        sysconfig.set_hostname(json.loads(request.data)["hostname"])
    return jsonify(hostname=sysconfig.get_hostname())

@backend.route('/config/timezone', methods=["GET", "PUT"])
@auth.required()
def timezone():
    if request.method == "PUT":
        sysconfig.set_timezone(**json.loads(request.data)["timezone"])
    return jsonify(timezone=sysconfig.get_timezone())

@backend.route('/config/datetime', methods=["GET", "PUT"])
@auth.required()
def datetime():
    if request.method == "PUT":
        systemtime.set_datetime()
    return jsonify(datetime={"datetime": systemtime.get_iso_time(), "offset": systemtime.get_offset()})

@backend.route('/system/shutdown', methods=["POST",])
@auth.required()
def shutdown():
    sysconfig.shutdown()

@backend.route('/system/reboot', methods=["POST",])
@auth.required()
def reboot():
    sysconfig.reboot()
