# process_job_details.py
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List

# Add models to path
sys.path.insert(0, str(Path(__file__).parent / "models"))
from models import JobDetail

def process_all_job_details():
    """Process all raw job detail files and create JobDetail objects"""
    detail_dir = Path("job_details")
    
    # Find all job detail JSON files (excluding summary and all_details)
    detail_files = [f for f in detail_dir.glob("*.json") 
                   if not f.name.startswith("all_details") 
                   and not f.name.startswith("details_only")
                   and not f.name.startswith("raw_details")]
    
    print(f"📂 Found {len(detail_files)} job detail files")
    
    job_details: List[JobDetail] = []
    errors = []
    
    for file in detail_files:
        try:
            with open(file, 'r') as f:
                data = json.load(f)
            
            # Create JobDetail object
            job_detail = JobDetail(**data)
            job_details.append(job_detail)
            print(f"✅ Processed: {job_detail.title} at {job_detail.company}")
            
        except Exception as e:
            errors.append(f"❌ Failed to process {file.name}: {str(e)}")
    
    print(f"\n📊 Summary:")
    print(f"   Total files: {len(detail_files)}")
    print(f"   Successfully processed: {len(job_details)}")
    print(f"   Errors: {len(errors)}")
    
    if errors:
        print("\n⚠️ Errors:")
        for error in errors[:5]:
            print(f"   {error}")
    
    # Save all processed job details
    if job_details:
        output_file = detail_dir / f"processed_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump([job.dict() for job in job_details], f, indent=2, default=str)
        print(f"\n💾 Saved {len(job_details)} processed details to {output_file}")
    
    return job_details

if __name__ == "__main__":
    process_all_job_details()
