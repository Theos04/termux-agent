#!/bin/bash
# One-click launcher for Naukri Job Bot

echo "🚀 Naukri Job Bot Launcher"
echo "=========================="
echo ""

# Check if token exists
if [ ! -f "naukri_token.txt" ]; then
    echo "🔑 No token found. Extracting from HAR file..."
    python extract_token_from_har.py
    
    # Check if token was extracted
    if [ ! -f "naukri_token.txt" ]; then
        echo "❌ Could not extract token. Please run manually:"
        echo "   python extract_token_from_har.py"
        exit 1
    fi
fi

# Run the bot
echo "🚀 Starting Naukri Job Bot..."
python naukri_job_bot.py
