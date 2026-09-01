# extract_naukri_apis_fixed.py
import json
import os
from datetime import datetime
from collections import defaultdict

def load_har_analysis(har_file):
    """Load the advanced analysis from HAR"""
    analysis_file = har_file.replace('.har', '_advanced_analysis.json')
    if os.path.exists(analysis_file):
        with open(analysis_file, 'r') as f:
            data = json.load(f)
            print(f"✅ Loaded analysis from: {analysis_file}")
            return data
    else:
        print(f"❌ Analysis file not found: {analysis_file}")
        return None

def extract_real_apis(analysis):
    """Extract real API endpoints from the analysis"""
    apis = []
    
    # Check token_correlation for real API endpoints
    if 'token_correlation' in analysis:
        token_data = analysis['token_correlation']
        for endpoint, info in token_data.items():
            # Check if it's a real API (not static asset)
            if not any(ext in endpoint for ext in ['.js', '.css', '.woff', '.png', '.jpg', '.svg']):
                apis.append({
                    'endpoint': endpoint,
                    'type': 'token_correlation',
                    'info': info
                })
    
    return apis

def extract_sensitive_data(analysis):
    """Extract sensitive data findings"""
    if 'sensitive_data' in analysis:
        data = analysis['sensitive_data']
        # Handle both dict and list formats
        if isinstance(data, dict):
            return data
        elif isinstance(data, list):
            # Convert list to dict with counts
            result = {}
            for item in data:
                if isinstance(item, dict):
                    for key, value in item.items():
                        result[key] = result.get(key, 0) + (value if isinstance(value, (int, float)) else 1)
                elif isinstance(item, str):
                    result[item] = result.get(item, 0) + 1
            return result
    return {}

def main():
    # Load the HAR analysis
    analysis = load_har_analysis('har_capture_20260802_161434.har')
    if not analysis:
        print("❌ No analysis file found.")
        return
    
    print("\n📊 Analysis Structure:")
    print(f"   Keys: {list(analysis.keys())}")
    
    # Extract real APIs from token_correlation
    real_apis = extract_real_apis(analysis)
    
    print(f"\n🔗 Found {len(real_apis)} real API endpoints")
    
    # Categorize APIs
    api_categories = defaultdict(list)
    for api in real_apis:
        endpoint = api['endpoint']
        if 'cloudgateway' in endpoint:
            # Extract the service name
            parts = endpoint.split('/')
            for part in parts:
                if 'cloudgateway' in part:
                    service = part
                    break
            else:
                service = 'cloudgateway'
            api_categories[service].append(api)
        elif 'jobapi' in endpoint:
            api_categories['jobapi'].append(api)
        elif 'servicegateway' in endpoint:
            service = endpoint.split('/')[0] if '/' in endpoint else 'servicegateway'
            api_categories[service].append(api)
        else:
            api_categories['other'].append(api)
    
    print("\n📂 API Categories:")
    for category, apis in api_categories.items():
        print(f"   • {category}: {len(apis)} endpoints")
    
    # Display the most interesting APIs
    print("\n🎯 Key Job-Related APIs:")
    print("=" * 60)
    
    job_keywords = ['job', 'recommend', 'search', 'inventory', 'dashboard', 'notification']
    
    for api in real_apis:
        endpoint = api['endpoint'].lower()
        if any(keyword in endpoint for keyword in job_keywords):
            print(f"\n🔹 {api['endpoint']}")
            if isinstance(api['info'], dict):
                for key, value in api['info'].items():
                    if key != 'token':  # Don't print full token
                        print(f"   {key}: {value}")
    
    # Extract and display sensitive data
    sensitive = extract_sensitive_data(analysis)
    print("\n" + "=" * 60)
    print("🛡️ Sensitive Data Summary:")
    if sensitive:
        if isinstance(sensitive, dict):
            for data_type, count in sensitive.items():
                print(f"   • {data_type}: {count}")
        elif isinstance(sensitive, list):
            for item in sensitive:
                print(f"   • {item}")
    else:
        print("   No sensitive data found")
    
    # Create a clean API list for use
    clean_apis = []
    for api in real_apis:
        clean_apis.append({
            'endpoint': api['endpoint'],
            'method': api['info'].get('method', 'GET') if isinstance(api['info'], dict) else 'GET'
        })
    
    # Save the real APIs
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_real_apis': len(real_apis),
        'api_categories': {k: len(v) for k, v in api_categories.items()},
        'apis': clean_apis,
        'sensitive_data': sensitive,
        'all_data': analysis
    }
    
    with open('naukri_real_apis.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n💾 Real APIs saved to: naukri_real_apis.json")
    
    # Show summary
    print("\n📊 Summary:")
    print(f"   • Real API endpoints: {len(real_apis)}")
    print(f"   • API Categories: {len(api_categories)}")
    
    # Show the most important APIs for job extraction
    print("\n🎯 Most Important APIs for Job Extraction:")
    job_apis = ['/jobapi/v2/search/recom-jobs', 
                '/cloudgateway-ccs/inventory-management-services/v2/page/pagename/ni-desktop-reco-v2',
                '/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard']
    
    for api_path in job_apis:
        found = False
        for api in real_apis:
            if api_path in api['endpoint']:
                print(f"   ✅ {api_path}")
                found = True
                break
        if not found:
            print(f"   ❌ {api_path} (not found in analysis)")
    
    print("\n💡 Next Steps:")
    print("   1. Run: python call_naukri_apis.py")
    print("   2. This will use the bearer token to call these APIs")
    print("   3. Extract job data directly from the API responses")

if __name__ == "__main__":
    main()
