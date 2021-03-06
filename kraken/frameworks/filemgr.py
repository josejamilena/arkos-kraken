import grp
import json
import mimetypes
import os
import pwd
import shutil
import stat

from arkos import shared_files
from arkos.system import users, groups
from arkos.utilities import b64_to_path, path_to_b64, compress, extract, str_fperms, random_string

from kraken import auth
from flask import Response, Blueprint, jsonify, request, abort
from flask.views import MethodView
from kraken.messages import remove_record
from kraken.utilities import as_job, job_response

backend = Blueprint("filemgr", __name__)


class FileManagerAPI(MethodView):
    @auth.required()
    def get(self, path):
        path = b64_to_path(path)
        if not path or not os.path.exists(path):
            abort(404)
        if os.path.isdir(path):
            data = []
            for x in os.listdir(path):
                data.append(as_dict(os.path.join(path, x)))
            return jsonify(files=data)
        else:
            return jsonify(file=as_dict(path, content=request.args.get("content", False)))
    
    @auth.required()
    def post(self, path):
        path = b64_to_path(path)
        if not os.path.exists(path):
            abort(404)
        if not os.path.isdir(path):
            resp = jsonify(message="Can only upload into folders")
            resp.status_code = 422
            return resp
        if request.headers.get('Content-Type').startswith("multipart/form-data"):
            f = request.files.get("file")
            if type(f) == list:
                for x in f:
                    filename = secure_filename(x.filename)
                    x.save(os.path.join(path, filename))
            else:
                filename = secure_filename(f.filename)
                f.save(os.path.join(path, filename))
            results = []
            for x in os.listdir(path):
                results.append(as_dict(os.path.join(path, x)))
        else:
            data = json.loads(request.data)["file"]
            if not os.path.exists(path):
                abort(404)
            if not os.path.isdir(path):
                resp = jsonify(message="Can only create into folders")
                resp.status_code = 422
                return resp
            if data["folder"]:
                os.makedirs(os.path.join(path, data["name"]))
            else:
                with open(os.path.join(path, data["name"]), 'w') as f:
                    f.write("")
            return jsonify(file=as_dict(os.path.join(path, data["name"])))
    
    @auth.required()
    def put(self, path):
        data = json.loads(request.data)["file"]
        if not os.path.exists(data["path"]):
            abort(404)
        if data["operation"] == "copy":
            if os.path.exists(os.path.join(data["newdir"], data["name"])):
                data["name"] = data["name"]+"-copy"
            if os.path.isdir(data["path"]):
                shutil.copytree(data["path"], os.path.join(data["newdir"], data["name"]))
            else:
                shutil.copy2(data["path"], os.path.join(data["newdir"], data["name"]))
            return jsonify(file=as_dict(os.path.join(data["newdir"], data["name"])))
        elif data["operation"] == "rename":
            shutil.move(data["path"], os.path.join(os.path.split(join(data["path"]))[0], data["name"]))
        elif data["operation"] == "edit":
            with open(data["path"], "w") as f:
                f.write(data["data"])
            return jsonify(file=as_dict(data["path"]))
        elif data["operation"] == "props":
            orig = as_dict(data["path"])
            if data["user"] != orig["user"] or data["group"] != orig["group"]:
                uid, gid = None, None
                u, g = users.get_system(data["user"]), groups.get_system(data["group"])
                if data["user"] == "root":
                    uid = 0
                if data["group"] == "root":
                    gid = 0
                if u and g:
                    uid, gid = u.uid, g.gid
                if uid == None or gid == None:
                    resp = jsonify(message="Invalid user/group specification")
                    resp.status_code = 422
                    return resp
                if data["folder"]:
                    os.chown(data["path"], uid, gid)
                    for r, d, f in os.walk(data["path"]):
                        for x in d:
                            os.chown(os.path.join(r, x), uid, gid)
                        for x in f:
                            os.chown(os.path.join(r, x), uid, gid)
                else:
                    os.chown(data["path"], u.uid, g.gid)
            if data["perms"]["oct"] != orig["perms"]["oct"]:
                if data["folder"]:
                    os.chmod(data["path"], int(data["perms"]["oct"][1:], 8))
                    for r, d, f in os.walk(data["path"]):
                        for x in d:
                            os.chmod(os.path.join(r, x), int(data["perms"]["oct"][1:], 8))
                        for x in f:
                            os.chmod(os.path.join(r, x), int(data["perms"]["oct"][1:], 8))
                else:
                    os.chmod(data["path"], int(data["perms"]["oct"][1:], 8))
            return jsonify(file=as_dict(data["path"]))
        else:
            abort(422)
    
    @auth.required()
    def delete(self, path):
        path = b64_to_path(path)
        if not os.path.exists(path):
            abort(404)
        try:
            if os.path.islink(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.unlink(path)
            return Response(status=204)
        except:
            abort(404)


class SharingAPI(MethodView):
    @auth.required()
    def get(self, id):
        shares = shared_files.get(id)
        if id and not shares:
            abort(404)
        if type(shares) == list:
            return jsonify(shares=[x.as_dict() for x in shares])
        else:
            return jsonify(share=shares.as_dict())
    
    @auth.required()
    def post(self):
        data = request.get_json()["share"]
        id = random_string()
        share = shared_files.Share(id, data["path"], data.get("expires", 0))
        share.add()
        return jsonify(share=share.as_dict())
    
    @auth.required()
    def put(self, id):
        share = shared_files.get(id)
        if id and not share:
            abort(404)
        data = request.get_json()["share"]
        if data["expires"]:
            share.update_expiry(data["expires_at"])
        else:
            share.update_expiry(False)
        return jsonify(share=share.as_dict())
    
    @auth.required()
    def delete(self, id):
        item = shared_files.get(id)
        if not item:
            abort(404)
        item.delete()
        return Response(status=204)


@backend.route("/shared/<string:id>", methods=["GET",])
def download(id):
    item = shared_files.get(id)
    if not item:
        abort(404)
    if item.is_expired():
        item.delete()
        resp = jsonify(message="The requested item has expired")
        resp.status_code = 410
        return resp
    if item.expires == 0:
        item.delete()
        remove_record("share", item.id)
    path = item.path
    item.fetch_count += 1
    if os.path.isdir(path):
        apath = compress(path, format="zip")
        with open(apath, "r") as f:
            data = f.read()
        resp = Response(data, mimetype="application/octet-stream")
        resp.headers["Content-Length"] = os.path.getsize(apath)
        resp.headers["Content-Disposition"] = "attachment; filename=%s" % os.path.basename(apath)
        return resp
    else: 
        with open(path, "r") as f:
            data = f.read()
        resp = Response(data, mimetype="application/octet-stream")
        resp.headers["Content-Length"] = str(len(data.encode('utf-8')))
        resp.headers["Content-Disposition"] = "attachment; filename=%s" % os.path.basename(path)
        return resp


def as_dict(path, content=False):
    name = os.path.basename(path)
    data = {"id": path_to_b64(path), "name": name, "path": path, "folder": False, 
        "hidden": name.startswith(".")}
    fstat = os.lstat(path)
    mode = fstat[stat.ST_MODE]
    
    if os.path.ismount(path):
        data["type"] = "mount"
        data["folder"] = True
        data["icon"] = "fa-hdd-o"
    elif stat.S_ISLNK(mode):
        data["type"] = "link"
        data["realpath"] = os.path.realpath(path)
        data["folder"] = os.path.isdir(data["realpath"])
        data["icon"] = "fa-link"
    elif stat.S_ISDIR(mode):
        data["type"] = "folder"
        data["folder"] = True
        data["icon"] = "fa-folder"
    elif stat.S_ISSOCK(mode):
        data["type"] = "socket"
        data["icon"] = "fa-plug"
    elif stat.S_ISBLK(mode):
        data["type"] = "block"
        data["icon"] = "fa-hdd-o"
    elif stat.S_ISREG(mode):
        data["type"] = "file"
        data["icon"] = guess_file_icon(name)
    else:
        data["type"] = "unknown"
        data["icon"] = "fa-question-circle"
    try:
        data["perms"] = {"oct": oct(stat.S_IMODE(mode)), "str": str_fperms(mode)}
        data["size"] = fstat[stat.ST_SIZE]
    except:
        return
    try:
        data["user"] = pwd.getpwuid(fstat[stat.ST_UID])[0]
    except:
        data["user"] = str(fstat[stat.ST_UID])
    try:
        data["group"] = grp.getgrgid(fstat[stat.ST_GID])[0]
    except:
        data["group"] = str(fstat[stat.ST_GID])
    if data["type"] == "file":
        tc = "".join(map(chr, [7,8,9,10,12,13,27] + range(0x20, 0x100)))
        ibs = lambda b: bool(b.translate(None, tc))
        with open(path, 'r') as f:
            try:
                data["binary"] = ibs(f.read(1024))
            except:
                data["binary"] = True
    else:
        data["binary"] = False
    data["mimetype"] = mimetypes.guess_type(path)[0]
    data["selected"] = False
    if content:
        with open(path, "r") as f:
            data["content"] = f.read()
    return data

def guess_file_icon(name):
    if name.endswith((".xls", ".xlsx", ".ods")):
        return "fa-file-excel-o"
    elif name.endswith((".mp3", ".wav", ".flac", ".ogg", ".m4a", ".wma", ".aac")):
        return "fa-file-audio-o"
    elif name.endswith((".mkv", ".avi", ".mov", ".wmv", ".mp4", ".m4v", ".mpg")):
        return "fa-file-video-o"
    elif name.endswith(".pdf"):
        return "fa-file-pdf-o"
    elif name.endswith((".ppt", ".pptx", ".odp")):
        return "fa-file-powerpoint-o"
    elif name.endswith((".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp")):
        return "fa-file-image-o"
    elif name.endswith((".zip", ".tar", ".gz", ".bz2", ".rar")):
        return "fa-file-archive-o"
    elif name.endswith((".doc", ".docx", ".odt")):
        return "fa-file-word-o"
    elif name.endswith((".php", ".js", ".py", ".sh", ".html", ".xml", ".rb", ".css")):
        return "fa-file-code-o"
    else:
        return "fa-file-o"


filemgr_view = FileManagerAPI.as_view('filemgr_api')
backend.add_url_rule('/files/<string:path>', view_func=filemgr_view, 
    methods=['GET', 'POST', 'PUT', 'DELETE'])
shares_view = SharingAPI.as_view('sharing_api')
backend.add_url_rule('/shares', defaults={"id": None}, view_func=shares_view, 
    methods=['GET',])
backend.add_url_rule('/shares', view_func=shares_view, methods=['POST',])
backend.add_url_rule('/shares/<string:id>', view_func=shares_view, 
    methods=['GET', 'PUT', 'DELETE'])
