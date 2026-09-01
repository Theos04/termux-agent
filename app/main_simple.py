from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import json
import os
from datetime import datetime
import uvicorn

app = FastAPI(title="Workflow Builder - Simple")
templates = Jinja2Templates(directory="templates")

# Simple file-based storage (no SQLAlchemy)
DATA_FILE = "workflow_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {"workflows": [], "next_id": 1, "next_box_id": 1}
    return {"workflows": [], "next_id": 1, "next_box_id": 1}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    data = load_data()
    return templates.TemplateResponse("index_simple.html", {
        "request": request,
        "workflows": data["workflows"]
    })

@app.get("/workflow/{workflow_id}", response_class=HTMLResponse)
async def view_workflow(request: Request, workflow_id: int):
    data = load_data()
    workflow = next((w for w in data["workflows"] if w["id"] == workflow_id), None)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return templates.TemplateResponse("workflow_simple.html", {
        "request": request,
        "workflow": workflow,
        "boxes": workflow.get("boxes", [])
    })

@app.post("/api/workflows")
async def create_workflow(name: str = Form(...), description: str = Form("")):
    data = load_data()
    workflow = {
        "id": data["next_id"],
        "name": name,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "boxes": []
    }
    data["workflows"].append(workflow)
    data["next_id"] += 1
    save_data(data)
    return RedirectResponse(url=f"/workflow/{workflow['id']}", status_code=303)

@app.post("/api/workflows/{workflow_id}/boxes")
async def create_box(
    workflow_id: int, 
    title: str = Form(...), 
    content: str = Form(""), 
    color: str = Form("#4CAF50")
):
    data = load_data()
    workflow = next((w for w in data["workflows"] if w["id"] == workflow_id), None)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    box = {
        "id": data["next_box_id"],
        "title": title,
        "content": content,
        "color": color,
        "order": len(workflow["boxes"]),
        "position_x": 50 + (len(workflow["boxes"]) * 20),
        "position_y": 50 + (len(workflow["boxes"]) * 20)
    }
    workflow["boxes"].append(box)
    data["next_box_id"] += 1
    save_data(data)
    return RedirectResponse(url=f"/workflow/{workflow_id}", status_code=303)

@app.delete("/api/boxes/{box_id}")
async def delete_box(box_id: int):
    data = load_data()
    for workflow in data["workflows"]:
        box = next((b for b in workflow["boxes"] if b["id"] == box_id), None)
        if box:
            workflow["boxes"].remove(box)
            # Reorder
            for idx, b in enumerate(workflow["boxes"]):
                b["order"] = idx
            save_data(data)
            return {"message": "Box deleted"}
    raise HTTPException(status_code=404, detail="Box not found")

@app.put("/api/boxes/{box_id}")
async def update_box(
    box_id: int, 
    title: str = Form(None), 
    content: str = Form(None), 
    color: str = Form(None)
):
    data = load_data()
    for workflow in data["workflows"]:
        box = next((b for b in workflow["boxes"] if b["id"] == box_id), None)
        if box:
            if title is not None:
                box["title"] = title
            if content is not None:
                box["content"] = content
            if color is not None:
                box["color"] = color
            save_data(data)
            return {"message": "Box updated"}
    raise HTTPException(status_code=404, detail="Box not found")

@app.post("/api/boxes/reorder")
async def reorder_boxes(request: Request):
    data = await request.json()
    box_order = data.get("boxes", [])
    
    # Find the workflow containing these boxes
    workflow_data = load_data()
    for workflow in workflow_data["workflows"]:
        for item in box_order:
            box = next((b for b in workflow["boxes"] if b["id"] == item["id"]), None)
            if box:
                box["order"] = item["order"]
                box["position_x"] = item.get("position_x", 50)
                box["position_y"] = item.get("position_y", 50)
    
    save_data(workflow_data)
    return {"message": "Boxes reordered"}

@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int):
    data = load_data()
    data["workflows"] = [w for w in data["workflows"] if w["id"] != workflow_id]
    save_data(data)
    return {"message": "Workflow deleted"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "tailscale_ip": "100.93.132.97",
        "framework": "FastAPI (file-based)"
    }

if __name__ == "__main__":
    print("🚀 Starting Workflow Builder (FastAPI - File based)")
    print("📍 Local: http://localhost:8000")
    print("📍 Tailscale: http://100.93.132.97:8000")
    print("📋 Press Ctrl+C to stop")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
