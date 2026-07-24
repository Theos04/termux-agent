# update_workflow_step.py
import json
from pathlib import Path

workflow_id = "f1723bd0-862"  # Your workflow ID
workflow_file = Path.home() / f"chrome-workflows/workflows/{workflow_id}/workflow.json"

with open(workflow_file, 'r') as f:
    workflow = json.load(f)

# Update the JS execution step with the working code
for step in workflow['steps']:
    if step.get('type') == 'js_execute':
        step['code'] = '''(function(){
    const jobs = [];
    document.querySelectorAll("app-competition-listing").forEach(function(l){
        const link = l.querySelector("a.item");
        if(link){
            jobs.push({
                title: link.querySelector("h3[itemprop=\\"name\\"]")?.textContent?.trim()||"N/A",
                company: link.querySelector("p.single-wrap")?.textContent?.trim()||"N/A",
                location: link.querySelector(".job_location")?.textContent?.trim()||"N/A",
                url: link.getAttribute("href")||"N/A",
                skills: Array.from(link.querySelectorAll(".un-el-chip-content .chip_text")).map(function(s){return s.textContent.trim()})
            });
        }
    });
    return {
        totalJobs: jobs.length,
        timestamp: new Date().toISOString(),
        jobs: jobs
    };
})()'''
        break

# Save the updated workflow
with open(workflow_file, 'w') as f:
    json.dump(workflow, f, indent=2)

print(f"✅ Updated workflow step for workflow: {workflow_id}")
print(f"   Workflow name: {workflow.get('name', 'Unknown')}")
print(f"   Steps: {len(workflow.get('steps', []))}")

