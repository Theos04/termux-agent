# analyze_payment_har.py
import json
import base64
import gzip

def analyze_har(filename):
    print(f"\n{'='*80}")
    print(f"Analyzing: {filename}")
    print(f"{'='*80}")
    
    with open(filename, 'r') as f:
        har = json.load(f)
    
    entries = har.get('log', {}).get('entries', [])
    print(f"Total entries: {len(entries)}")
    
    # Find all API calls to agoda
    api_calls = []
    for entry in entries:
        url = entry.get('request', {}).get('url', '')
        if 'agoda.com/api' in url:
            status = entry.get('response', {}).get('status', 0)
            method = entry.get('request', {}).get('method', '')
            api_calls.append((status, method, url))
    
    print(f"\nFound {len(api_calls)} API calls:")
    for status, method, url in sorted(api_calls):
        # Decode URL for readability
        import urllib.parse
        decoded = urllib.parse.unquote(url)
        if len(decoded) > 100:
            decoded = decoded[:100] + "..."
        print(f"  {status} {method} {decoded}")
    
    # Specifically look for payment-related requests
    print(f"\n{'='*80}")
    print("Payment-specific requests:")
    print(f"{'='*80}")
    
    payment_requests = []
    for entry in entries:
        url = entry.get('request', {}).get('url', '')
        if 'payment' in url.lower() or 'book' in url.lower():
            status = entry.get('response', {}).get('status', 0)
            method = entry.get('request', {}).get('method', '')
            body = entry.get('request', {}).get('postData', {})
            response = entry.get('response', {})
            
            payment_requests.append({
                'status': status,
                'method': method,
                'url': url,
                'body': body.get('text', '') if body else '',
                'response_body': response.get('content', {}).get('text', '')
            })
    
    for req in payment_requests:
        print(f"\nStatus: {req['status']}")
        print(f"URL: {req['url']}")
        if req['body']:
            print(f"Body: {req['body'][:500]}...")
        if req['response_body']:
            print(f"Response: {req['response_body'][:300]}...")
        print("-" * 40)

# Analyze all your HAR files
analyze_har('agoda_1.har')
