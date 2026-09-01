#!/bin/bash
# Simple launcher for Naukri Job Bot

echo "🚀 Naukri Job Bot"
echo "================="
echo ""

# Check if token exists
if [ ! -f "naukri_token.txt" ]; then
    echo "🔑 No token found."
    echo ""
    echo "Options:"
    echo "  1. Run manual token entry"
    echo "  2. Try extracting from HAR file"
    echo "  3. Enter token now"
    echo ""
    read -p "Select option (1-3): " option
    
    case $option in
        1)
            python get_token_manual.py
            ;;
        2)
            python extract_token_from_har.py
            ;;
        3)
            read -p "Enter your token: " token
            echo $token > naukri_token.txt
            echo "✅ Token saved"
            ;;
        *)
            echo "Invalid option"
            exit 1
            ;;
    esac
fi

# Check if token file has content
if [ -f "naukri_token.txt" ]; then
    TOKEN=$(cat naukri_token.txt)
    if [ -z "$TOKEN" ]; then
        echo "❌ Token file is empty. Please run token extraction again."
        exit 1
    fi
    echo "✅ Token found: ${TOKEN:0:30}..."
    echo ""
    echo "🚀 Starting job bot..."
    python naukri_job_bot_fixed.py
else
    echo "❌ Token file not found."
    exit 1
fi
