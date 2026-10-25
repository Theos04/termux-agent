#!/data/data/com.termux/files/usr/bin/bash
# Run Unstop hackathon extractor with pagination

echo "🏆 Unstop Hackathon Extractor with Pagination"
echo "=============================================="

# Check for Chrome
if ! curl -s http://127.0.0.1:9258/json > /dev/null 2>&1; then
    echo "❌ Chrome not running with remote debugging on port 9258"
    exit 1
fi

# Run the script
python3 unstop_with_pagination.py

# Show results
echo ""
echo "📊 Results:"
ls -lh hackathon_urls_*.txt hackathon_details*.json 2>/dev/null
