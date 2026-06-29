from flask import Flask, request, jsonify
from cdpv114 import get_manager

app = Flask(__name__)

manager = get_manager()


@app.get("/")
def home():
    return {
        "name": "Chrome Session Manager",
        "status": "running"
    }


@app.get("/sessions")
def sessions():
    return jsonify(manager.db.list_sessions())


@app.get("/session/<int:session_id>")
def session(session_id):
    s = manager.db.get_session(session_id)

    if not s:
        return jsonify({"error": "Not found"}), 404

    return jsonify(s)


@app.post("/session")
def create():

    data = request.json

    name = data["name"]
    url = data.get("url", "https://google.com")

    port = manager._get_next_port()

    profile_dir = f"{manager.config.base_profile_dir}/{name}"

    session_id = manager.db.create_session(
        name=name,
        url=url,
        port=port,
        profile_dir=profile_dir
    )

    return jsonify({
        "session_id": session_id,
        "port": port
    })


@app.post("/session/<int:id>/start")
def start(id):

    manager.start_session(id)

    return jsonify({
        "success": True
    })


@app.post("/session/<int:id>/stop")
def stop(id):

    manager.stop_session(id)

    return jsonify({
        "success": True
    })


@app.delete("/session/<int:id>")
def delete(id):

    manager.delete_session(id)

    return jsonify({
        "success": True
    })


@app.get("/session/<int:id>/tabs")
def tabs(id):

    session = manager.db.get_session(id)

    if not session:
        return jsonify({"error": "Not found"}), 404

    devtools = manager._get_devtools(session["port"])

    return jsonify(devtools.get_tabs())


@app.get("/session/<int:id>/ws")
def websocket_urls(id):

    session = manager.db.get_session(id)

    if not session:
        return jsonify({"error": "Not found"}), 404

    devtools = manager._get_devtools(session["port"])

    return jsonify(devtools.get_ws_urls())


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True
    )
