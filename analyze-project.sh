#!/bin/bash
# Complete project analysis with visual output

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     ${GREEN}📊 Chrome Launcher Project Analysis${CYAN}                  ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Run full analysis
python3 ~/automation/chrome-launcher/code_analyzer.py . --json

# Get the latest report
LATEST_REPORT=$(ls -t analysis_*/analysis_*.md 2>/dev/null | head -1)
LATEST_JSON=$(ls -t analysis_*/analysis_*.json 2>/dev/null | head -1)

if [ -n "$LATEST_REPORT" ]; then
    echo -e "\n${GREEN}📊 Analysis Complete!${NC}"
    echo ""
    
    # Extract key metrics
    echo -e "${BLUE}📈 Key Metrics:${NC}"
    grep -E "Total Files:|Total Lines:|Total Classes:|Total Functions:|Total Methods:" "$LATEST_REPORT" | sed 's/^/  /'
    
    echo ""
    echo -e "${YELLOW}🔍 Design Patterns Found:${NC}"
    grep -A5 "Design Patterns" "$LATEST_REPORT" | grep "✓" | sed 's/^/  /'
    
    echo ""
    echo -e "${RED}⚠️  Anti-Patterns Detected:${NC}"
    grep -A5 "Anti-Patterns" "$LATEST_REPORT" | grep "✗" | sed 's/^/  /'
    
    echo ""
    echo -e "${CYAN}📁 Report saved to:${NC} $LATEST_REPORT"
    if [ -n "$LATEST_JSON" ]; then
        echo -e "${CYAN}📁 JSON saved to:${NC} $LATEST_JSON"
    fi
fi
