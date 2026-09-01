from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///./workflow.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models
class Workflow(db.Model):
    __tablename__ = 'workflows'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    boxes = db.relationship('Box', backref='workflow', lazy=True, cascade='all, delete-orphan')

class Box(db.Model):
    __tablename__ = 'boxes'
    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey('workflows.id'))
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text)
    position_x = db.Column(db.Integer, default=0)
    position_y = db.Column(db.Integer, default=0)
    order = db.Column(db.Integer, default=0)
    color = db.Column(db.String(7), default='#4CAF50')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Create tables
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    workflows = Workflow.query.all()
    return render_template('index_flask.html', workflows=workflows)

@app.route('/workflow/<int:workflow_id>')
def view_workflow(workflow_id):
    workflow = Workflow.query.get_or_404(workflow_id)
    boxes = Box.query.filter_by(workflow_id=workflow_id).order_by(Box.order).all()
    return render_template('workflow_flask.html', workflow=workflow, boxes=boxes)

@app.route('/api/workflows', methods=['POST'])
def create_workflow():
    name = request.form.get('name')
    description = request.form.get('description', '')
    
    if not name:
        return redirect(url_for('index'))
    
    workflow = Workflow(name=name, description=description)
    db.session.add(workflow)
    db.session.commit()
    
    return redirect(url_for('view_workflow', workflow_id=workflow.id))

@app.route('/api/workflows/<int:workflow_id>/boxes', methods=['POST'])
def create_box(workflow_id):
    workflow = Workflow.query.get_or_404(workflow_id)
    title = request.form.get('title')
    content = request.form.get('content', '')
    color = request.form.get('color', '#4CAF50')
    
    if not title:
        return redirect(url_for('view_workflow', workflow_id=workflow_id))
    
    max_order = Box.query.filter_by(workflow_id=workflow_id).count()
    box = Box(
        workflow_id=workflow_id,
        title=title,
        content=content,
        color=color,
        order=max_order,
        position_x=50 + (max_order * 20),
        position_y=50 + (max_order * 20)
    )
    db.session.add(box)
    db.session.commit()
    
    return redirect(url_for('view_workflow', workflow_id=workflow_id))

@app.route('/api/boxes/<int:box_id>', methods=['DELETE'])
def delete_box(box_id):
    box = Box.query.get_or_404(box_id)
    workflow_id = box.workflow_id
    
    db.session.delete(box)
    db.session.commit()
    
    # Reorder remaining boxes
    boxes = Box.query.filter_by(workflow_id=workflow_id).order_by(Box.order).all()
    for idx, b in enumerate(boxes):
        b.order = idx
    db.session.commit()
    
    return jsonify({'message': 'Box deleted'})

@app.route('/api/boxes/<int:box_id>', methods=['PUT'])
def update_box(box_id):
    box = Box.query.get_or_404(box_id)
    
    title = request.form.get('title')
    content = request.form.get('content')
    color = request.form.get('color')
    position_x = request.form.get('position_x', type=int)
    position_y = request.form.get('position_y', type=int)
    
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
    
    db.session.commit()
    return jsonify({'message': 'Box updated'})

@app.route('/api/boxes/reorder', methods=['POST'])
def reorder_boxes():
    data = request.get_json()
    box_order = data.get('boxes', [])
    
    for item in box_order:
        box = Box.query.get(item['id'])
        if box:
            box.order = item['order']
            box.position_x = item.get('position_x', box.position_x)
            box.position_y = item.get('position_y', box.position_y)
    
    db.session.commit()
    return jsonify({'message': 'Boxes reordered'})

@app.route('/api/workflows/<int:workflow_id>', methods=['DELETE'])
def delete_workflow(workflow_id):
    workflow = Workflow.query.get_or_404(workflow_id)
    db.session.delete(workflow)
    db.session.commit()
    return jsonify({'message': 'Workflow deleted'})

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'tailscale_ip': '100.93.132.97',
        'framework': 'Flask'
    })

if __name__ == '__main__':
    print("🚀 Starting Workflow Builder with Flask")
    print("📍 Local: http://localhost:8000")
    print("📍 Tailscale: http://100.93.132.97:8000")
    app.run(host='0.0.0.0', port=8000, debug=False)
