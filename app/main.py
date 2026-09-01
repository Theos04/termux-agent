# main.py - Working version for Termux
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
from typing import Optional
import uvicorn

# Database setup
DATABASE_URL = "sqlite:///./workflow.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class Workflow(Base):
    __tablename__ = "workflows"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    boxes = relationship("Box", back_populates="workflow", cascade="all, delete-orphan")

class Box(Base):
    __tablename__ = "boxes"
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    title = Column(String)
    content = Column(Text)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
    order = Column(Integer, default=0)
    color = Column(String, default="#4CAF50")
    created_at = Column(DateTime, default=datetime.utcnow)
    workflow = relationship("Workflow", back_populates="boxes")

# Create tables
Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="Workflow Builder")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    workflows = db.query(Workflow).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "workflows": workflows
    })

@app.get("/workflow/{workflow_id}", response_class=HTMLResponse)
async def view_workflow(request: Request, workflow_id: int, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    boxes = db.query(Box).filter(Box.workflow_id == workflow_id).order_by(Box.order).all()
    return templates.TemplateResponse("workflow.html", {
        "request": request,
        "workflow": workflow,
        "boxes": boxes
    })

@app.post("/api/workflows")
async def create_workflow(
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    workflow = Workflow(name=name, description=description)
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return RedirectResponse(url=f"/workflow/{workflow.id}", status_code=303)

@app.post("/api/workflows/{workflow_id}/boxes")
async def create_box(
    workflow_id: int,
    title: str = Form(...),
    content: str = Form(""),
    color: str = Form("#4CAF50"),
    db: Session = Depends(get_db)
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    max_order = db.query(Box).filter(Box.workflow_id == workflow_id).count()
    box = Box(
        workflow_id=workflow_id,
        title=title,
        content=content,
        color=color,
        order=max_order,
        position_x=50 + (max_order * 20),
        position_y=50 + (max_order * 20)
    )
    db.add(box)
    db.commit()
    db.refresh(box)
    return RedirectResponse(url=f"/workflow/{workflow_id}", status_code=303)

@app.delete("/api/boxes/{box_id}")
async def delete_box(box_id: int, db: Session = Depends(get_db)):
    box = db.query(Box).filter(Box.id == box_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="Box not found")
    
    workflow_id = box.workflow_id
    db.delete(box)
    db.commit()
    
    boxes = db.query(Box).filter(Box.workflow_id == workflow_id).order_by(Box.order).all()
    for idx, b in enumerate(boxes):
        b.order = idx
    db.commit()
    return {"message": "Box deleted"}

@app.put("/api/boxes/{box_id}")
async def update_box(
    box_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    position_x: Optional[int] = Form(None),
    position_y: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    box = db.query(Box).filter(Box.id == box_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="Box not found")
    
    if title is not None:
        box.title = title
    if content is not None:
        box.content = content
    if color is not None:
        box.color = color
    if position_x is not None:
        box.position_x = position_x
    if position_y is not None:
        box.position_y = position_y
    
    db.commit()
    return {"message": "Box updated"}

@app.post("/api/boxes/reorder")
async def reorder_boxes(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    box_order = data.get("boxes", [])
    
    for item in box_order:
        box = db.query(Box).filter(Box.id == item["id"]).first()
        if box:
            box.order = item["order"]
            box.position_x = item.get("position_x", box.position_x)
            box.position_y = item.get("position_y", box.position_y)
    
    db.commit()
    return {"message": "Boxes reordered"}

@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete(workflow)
    db.commit()
    return {"message": "Workflow deleted"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "tailscale_ip": "100.93.132.97"}

if __name__ == "__main__":
    print("🚀 Starting Workflow Builder on Tailscale network")
    print("📍 Local: http://localhost:8000")
    print("📍 Tailscale: http://100.93.132.97:8000")
    print("📋 Press Ctrl+C to stop")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
