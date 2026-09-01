import json
import re

def extract_job_data(accessibility_json):
    """Extract job posting data from WhatsApp accessibility tree JSON."""
    
    data = {
        "mrf_interview": {
            "title": None,
            "venue": None,
            "date": None,
            "time": None,
            "pre_registration": None,
            "application_link": None,
            "original_post_link": None,
            "forwarded": False
        },
        "mpsc_recruitment": {
            "title": None,
            "exam_name": None,
            "total_posts": None,
            "last_date": None,
            "extension_notice": None,
            "whatsapp_channel": None,
            "positions": [],
            "educational_qualification": None,
            "age_limit": None,
            "fee": {
                "open_category": None,
                "reserved_category": None
            }
        },
        "contacts": {
            "phone_numbers": [],
            "names": [],
            "emails": [],
            "groups": []
        }
    }
    
    # Extract text nodes
    text_nodes = []
    for node in accessibility_json.get("nodes", []):
        if node.get("role", {}).get("value") == "InlineTextBox":
            text_nodes.append(node.get("name", {}).get("value", ""))
    
    full_text = " ".join(text_nodes)
    
    # Extract MRF data
    mrf_patterns = {
        "title": r"MRF Walk-In Interview[^\n]*",
        "venue": r"Venue:[^\n]*",
        "date": r"Date:[^\n]*",
        "time": r"Time:[^\n]*",
        "pre_registration": r"Pre-registration[^\n]*",
        "application_link": r"https://lnkd\.in/[^\s]+",
        "original_post": r"https://www\.linkedin\.com/posts/[^\s]+"
    }
    
    for key, pattern in mrf_patterns.items():
        match = re.search(pattern, full_text)
        if match:
            if key == "title":
                data["mrf_interview"]["title"] = match.group(0)
            elif key == "venue":
                data["mrf_interview"]["venue"] = match.group(0).replace("Venue:", "").strip()
            elif key == "date":
                data["mrf_interview"]["date"] = match.group(0).replace("Date:", "").strip()
            elif key == "time":
                data["mrf_interview"]["time"] = match.group(0).replace("Time:", "").strip()
            elif key == "pre_registration":
                data["mrf_interview"]["pre_registration"] = match.group(0)
            elif key == "application_link":
                data["mrf_interview"]["application_link"] = match.group(0)
            elif key == "original_post":
                data["mrf_interview"]["original_post_link"] = match.group(0)
    
    # Extract MPSC data
    if "MPSC" in full_text or "महाभरती" in full_text:
        # Title
        title_match = re.search(r"महाभरती[^!]*!", full_text)
        if title_match:
            data["mpsc_recruitment"]["title"] = title_match.group(0)
        
        # Exam name
        exam_match = re.search(r"MPSC[^!]*!", full_text)
        if exam_match:
            data["mpsc_recruitment"]["exam_name"] = exam_match.group(0)
        
        # Total posts
        posts_match = re.search(r"५,\d{3}|\d+,\d{3}", full_text)
        if posts_match:
            data["mpsc_recruitment"]["total_posts"] = posts_match.group(0)
        
        # Last date
        date_match = re.search(r"०६ ऑगस्ट २०२६|\d{2} \w+ \d{4}", full_text)
        if date_match:
            data["mpsc_recruitment"]["last_date"] = date_match.group(0)
        
        # Extension notice
        ext_match = re.search(r"तलाठी भरती[^!]+!", full_text)
        if ext_match:
            data["mpsc_recruitment"]["extension_notice"] = ext_match.group(0)
        
        # WhatsApp channel
        channel_match = re.search(r"https://whatsapp\.com/channel/[^\s]+", full_text)
        if channel_match:
            data["mpsc_recruitment"]["whatsapp_channel"] = channel_match.group(0)
        
        # Age limit
        age_match = re.search(r"\d+/\d+ ते \d+ वर्षे", full_text)
        if age_match:
            data["mpsc_recruitment"]["age_limit"] = age_match.group(0)
        
        # Fee
        open_fee = re.search(r"खुला प्रवर्ग: ₹\d+", full_text)
        if open_fee:
            data["mpsc_recruitment"]["fee"]["open_category"] = open_fee.group(0)
        
        reserved_fee = re.search(r"मागासवर्गीय/आर्थिकदृष्ट्या दुर्बल: ₹\d+", full_text)
        if reserved_fee:
            data["mpsc_recruitment"]["fee"]["reserved_category"] = reserved_fee.group(0)
    
    # Extract contacts
    phone_pattern = r"\+?[\d\s\-\(\)]{10,15}"
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    name_pattern = r"[A-Z][a-z]+ [A-Z][a-z]+(?: [A-Z][a-z]+)?"
    
    data["contacts"]["phone_numbers"] = list(set(re.findall(phone_pattern, full_text)))
    data["contacts"]["emails"] = list(set(re.findall(email_pattern, full_text)))
    
    # Filter names (exclude common false positives)
    names = set(re.findall(name_pattern, full_text))
    exclude = {"MRF", "India", "Venue", "Date", "Time", "August", "College", "Arts", "Science"}
    data["contacts"]["names"] = [n for n in names if n not in exclude and len(n.split()) >= 2]
    
    # Groups
    group_pattern = r"CTF players|unGhost\.in|Home Empire"
    data["contacts"]["groups"] = list(set(re.findall(group_pattern, full_text)))
    
    return data

# Usage
with open("a11y_131903_193546.json", "r") as f:
    data = json.load(f)

job_data = extract_job_data(data)
print(json.dumps(job_data, indent=2, ensure_ascii=False))
