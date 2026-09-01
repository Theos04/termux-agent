#!/data/data/com.termux/files/usr/bin/bash
# unstop_hackathons.sh - With proper waiting

echo "🚀 Starting Unstop Hackathon URL Mapper"
echo "========================================"

# Set up paths
BASE_DIR="/data/data/com.termux/files/home/automation/chrome-launcher"
SCRIPTS_DIR="${BASE_DIR}/scripts-library/unstop"
cd "${SCRIPTS_DIR}" || exit 1

# Check if Chrome session is running
echo "🔍 Checking Chrome session..."
curl -s http://127.0.0.1:5000/session/unstop/status || {
    echo "⚠️  No active session found. Starting new session..."
    curl -X POST http://127.0.0.1:5000/session/unstop/start \
        -H "Content-Type: application/json" \
        -d '{"url": "https://unstop.com/hackathons?oppstatus=open"}'
    echo "⏳ Waiting 15 seconds for initial page load..."
    sleep 15
}

# Run the quick extractor first
echo ""
echo "📊 Running quick URL extractor with 15s wait time..."
python3 quick_url_extractor.py

# Check results
if [ -f "quick_hackathon_urls.txt" ]; then
    echo ""
    echo "✅ Quick extraction complete!"
    echo "📋 Found $(wc -l < quick_hackathon_urls.txt) URLs"
    echo ""
    echo "📄 First 10 URLs:"
    head -10 quick_hackathon_urls.txt | sed 's/^/   /'
fi

# Ask if user wants to run the full mapper
echo ""
echo "========================================"
echo "Do you want to run the full mapper? (y/N)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "📊 Running full hackathon URL mapper..."
    python3 unstop_hackathon_mapper.py
    
    if [ -f "hackathon_urls.json" ]; then
        echo "✅ Results saved to hackathon_urls.json"
        echo "📋 Total hackathons found: $(jq '.total_hackathons' hackathon_urls.json 2>/dev/null || echo 'N/A')"
    fi
fi

echo "========================================"
echo "✅ Done!"
