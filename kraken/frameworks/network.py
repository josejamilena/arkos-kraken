import json

from flask import Response, Blueprint, abort, jsonify, request
from flask.views import MethodView

from kraken import auth
from arkos.system import network

backend = Blueprint("networks", __name__)


class NetworksAPI(MethodView):
    @auth.required()
    def get(self, id):
        nets = network.get_connections(id)
        if id and not nets:
            abort(404)
        if type(nets) == list:
            return jsonify(networks=[x.as_dict() for x in nets])
        else:
            return jsonify(network=nets.as_dict())
    
    @auth.required()
    def post(self):
        data = json.loads(request.data)["network"]
        net = network.Connection(id=data["id"], config=data["config"])
        net.add()
        return jsonify(network=net.as_dict())
    
    @auth.required()
    def put(self, id):
        data = json.loads(request.data)["network"]
        net = network.get_connections(id)
        if not id or not net:
            abort(404)
        if data.get("operation"):
            try:
                if data["operation"] == "connect":
                    net.connect()
                elif data["operation"] == "disconnect":
                    net.disconnect()
                elif data["operation"] == "enable":
                    net.enable()
                elif data["operation"] == "disable":
                    net.disable()
                else:
                    abort(422)
            except Exception, e:
                resp = jsonify(message=str(e))
                resp.status_code = 500
                return resp
        else:
            net.config = data["config"]
            net.update()
        return jsonify(network=net.as_dict())
    
    @auth.required()
    def delete(self, id):
        net = network.get_connections(id)
        if not id or not net:
            abort(404)
        net.remove()
        return Response(status=204)


@backend.route('/system/netifaces', defaults={'id': None})
@backend.route('/system/netifaces/<string:id>')
@auth.required()
def get_netifaces(id):
    ifaces = network.get_interfaces(id)
    if id and not ifaces:
        abort(404)
    if type(ifaces) == list:
        return jsonify(netifaces=[x.as_dict() for x in ifaces])
    else:
        return jsonify(netiface=ifaces.as_dict())


network_view = NetworksAPI.as_view('networks_api')
backend.add_url_rule('/system/networks', defaults={'id': None}, 
    view_func=network_view, methods=['GET',])
backend.add_url_rule('/system/networks', view_func=network_view, methods=['POST',])
backend.add_url_rule('/system/networks/<string:id>', view_func=network_view, 
    methods=['GET', 'PUT', 'DELETE'])
