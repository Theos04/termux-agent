# test_client.py
"""
Test client for Chrome Control Plane API
Tests all endpoints with the new Celery-based architecture
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:5000"

def print_response(title, response):
    """Pretty print API response"""
    print(f"\n{'='*60}")
    print(f"📋 {title}")
    print(f"{'='*60}")
    print(f"Status: {response.status_code}")
    try:
        data = response.json()
        print(json.dumps(data, indent=2, default=str))
    except:
        print(response.text)
    print(f"{'='*60}\n")

def test_health():
    """Test health endpoint"""
    print("\n🔍 Testing Health Check...")
    response = requests.get(f"{BASE_URL}/api/health")
    print_response("Health Check", response)
    return response.json()

def test_start_session():
    """Test starting a session"""
    print("\n🚀 Testing Start Session...")
    data = {
        "name": "test_session",
        "url": "https://unstop.com/",
        "wait": True,
        "timeout": 30
    }
    response = requests.post(
        f"{BASE_URL}/api/session/test_session/start",
        json=data
    )
    print_response("Start Session", response)
    return response.json()

def test_get_status():
    """Test getting session status"""
    print("\n📊 Testing Get Status...")
    response = requests.get(f"{BASE_URL}/api/session/test_session/status")
    print_response("Session Status", response)
    return response.json()

def test_execute_js():
    """Test executing JavaScript"""
    print("\n⚡ Testing Execute JavaScript...")
    data = {
        "script": """
            return {
                title: document.title,
                url: window.location.href,
                timestamp: new Date().toISOString()
            };
        """,
        "save_key": "page_info",
        "wait": True,
        "timeout": 30
    }
    response = requests.post(
        f"{BASE_URL}/api/session/test_session/execute",
        json=data
    )
    print_response("Execute JS", response)
    return response.json()

def test_extract_data():
    """Test extracting data"""
    print("\n📊 Testing Extract Data...")
    data = {
        "selector": "h1, .title, .heading",
        "key": "main_heading",
        "wait": True,
        "timeout": 30
    }
    response = requests.post(
        f"{BASE_URL}/api/session/test_session/extract",
        json=data
    )
    print_response("Extract Data", response)
    return response.json()

def test_extract_multiple():
    """Test extracting multiple selectors"""
    print("\n📊 Testing Extract Multiple...")
    data = {
        "selectors": {
            "title": "title",
            "heading": "h1",
            "description": "meta[name='description']:content",
            "links": "a:innerText"
        },
        "save_key": "page_metadata",
        "wait": True,
        "timeout": 30
    }
    response = requests.post(
        f"{BASE_URL}/api/session/test_session/extract/multiple",
        json=data
    )
    print_response("Extract Multiple", response)
    return response.json()

def test_save_html():
    """Test saving HTML"""
    print("\n💾 Testing Save HTML...")
    data = {
        "extract_title": True,
        "save_key": "html_content",
        "wait": True,
        "timeout": 30
    }
    response = requests.post(
        f"{BASE_URL}/api/session/test_session/save/html",
        json=data
    )
    print_response("Save HTML", response)
    return response.json()

def test_screenshot():
    """Test taking screenshot"""
    print("\n📸 Testing Screenshot...")
    response = requests.get(
        f"{BASE_URL}/api/session/test_session/screenshot?wait=true&save=true"
    )
    print_response("Screenshot", response)
    return response.json()

def test_get_session_data():
    """Test getting all session data"""
    print("\n📊 Testing Get Session Data...")
    response = requests.get(f"{BASE_URL}/api/session/test_session/data")
    print_response("Session Data", response)
    return response.json()

def test_batch_operations():
    """Test batch operations"""
    print("\n📦 Testing Batch Operations...")
    data = {
        "operations": [
            {"type": "evaluate", "params": {"expression": "document.title"}},
            {"type": "sleep", "params": {"seconds": 2}},
            {"type": "evaluate", "params": {"expression": "window.location.href"}},
            {"type": "extract", "params": {"selector": "h1"}}
        ],
        "stop_on_error": True,
        "wait": True,
        "timeout": 60
    }
    response = requests.post(
        f"{BASE_URL}/api/session/test_session/batch",
        json=data
    )
    print_response("Batch Operations", response)
    return response.json()

def test_list_sessions():
    """Test listing all sessions"""
    print("\n📋 Testing List Sessions...")
    response = requests.get(f"{BASE_URL}/api/sessions")
    print_response("List Sessions", response)
    return response.json()

def test_stop_session():
    """Test stopping a session"""
    print("\n⏹️ Testing Stop Session...")
    response = requests.post(
        f"{BASE_URL}/api/session/test_session/stop?wait=true"
    )
    print_response("Stop Session", response)
    return response.json()

def test_task_status():
    """Test getting task status"""
    print("\n🔍 Testing Task Status...")
    # First submit a task to get a task ID
    data = {
        "script": "document.title",
        "save_key": "test_title",
        "wait": False
    }
    response = requests.post(
        f"{BASE_URL}/api/session/test_session/execute",
        json=data
    )
    if response.status_code == 200:
        task_id = response.json().get('task_id')
        if task_id:
            # Now check status
            status_response = requests.get(f"{BASE_URL}/api/task/{task_id}/status")
            print_response(f"Task Status: {task_id}", status_response)
            return status_response.json()
    print("❌ Failed to get task ID")
    return None

def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "="*60)
    print("🧪 Chrome Control Plane API Test Suite")
    print("="*60)
    print(f"Starting at: {datetime.now().isoformat()}")
    print(f"API URL: {BASE_URL}")
    print("="*60)
    
    # Test health first
    try:
        health = test_health()
        if health.get('status') != 'ok':
            print("❌ Health check failed. Is the API running?")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Is it running?")
        print("   Start with: python api_enhanced.py")
        return
    
    # Run all tests
    test_start_session()
    time.sleep(2)
    
    test_get_status()
    time.sleep(1)
    
    test_execute_js()
    time.sleep(1)
    
    test_extract_data()
    time.sleep(1)
    
    test_extract_multiple()
    time.sleep(1)
    
    test_save_html()
    time.sleep(1)
    
    test_screenshot()
    time.sleep(1)
    
    test_batch_operations()
    time.sleep(1)
    
    test_get_session_data()
    time.sleep(1)
    
    test_list_sessions()
    time.sleep(1)
    
    test_task_status()
    time.sleep(1)
    
    test_stop_session()
    
    print("\n" + "="*60)
    print("✅ Test Suite Complete!")
    print("="*60)
    print("\n📊 Check Google Sheets for saved data:")
    print("   - chrome_sessions tab")
    print("   - extracted_data tab")
    print("   - page_data tab")
    print("   - screenshots tab")
    print("   - automation_results tab")
    print("   - tasks_log tab")

if __name__ == "__main__":
    run_all_tests()
