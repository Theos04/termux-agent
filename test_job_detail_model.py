# test_job_detail_model.py
import json
import sys
from pathlib import Path

# Add models to path
sys.path.insert(0, str(Path(__file__).parent / "models"))
from models import JobDetail

# Test with one of the extracted files
test_file = Path("job_details/business-development-executive-cutibless-healthcare-pvt-ltd-1718749.json")

if test_file.exists():
    with open(test_file, 'r') as f:
        data = json.load(f)
    
    print("📄 Testing JobDetail creation...")
    try:
        job_detail = JobDetail(**data)
        print("✅ JobDetail created successfully!")
        print(f"   Title: {job_detail.title}")
        print(f"   Company: {job_detail.company}")
        print(f"   Location: {job_detail.location}")
        print(f"   Job Type: {job_detail.job_type}")
        print(f"   Skills: {job_detail.skills}")
        print(f"   Eligibility: {job_detail.eligibility}")
        if job_detail.salary_range:
            print(f"   Salary: {job_detail.salary_range}")
        if job_detail.deadline:
            print(f"   Deadline: {job_detail.deadline}")
        print(f"   Detail URL: {job_detail.detail_url}")
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("❌ Test file not found")
