#!/bin/bash
# Show project structure with focus on key files

echo -e "\033[0;36m📁 Project Structure\033[0m"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Show directory structure with file counts
echo -e "\033[0;32m📊 Directory Overview:\033[0m"
find . -type d -not -path "*/\.*" -not -path "*/__pycache__*" | while read dir; do
    count=$(find "$dir" -maxdepth 1 -name "*.py" -type f 2>/dev/null | wc -l)
    if [ $count -gt 0 ]; then
        echo "  $(basename "$dir")/ - $count Python files"
    fi
done | sort

echo ""
echo -e "\033[0;34m📄 Key Files:\033[0m"

# Show main files
for file in cdpv119.py launch-chrome.py fpl.py fetch_page_llm5.py; do
    if [ -f "$file" ]; then
        classes=$(rg "^class " "$file" 2>/dev/null | wc -l | tr -d ' ')
        funcs=$(rg "^def " "$file" 2>/dev/null | wc -l | tr -d ' ')
        lines=$(cat "$file" 2>/dev/null | wc -l | tr -d ' ')
        echo "  📄 $file: $classes classes, $funcs functions, $lines lines"
    fi
done

echo ""
echo -e "\033[0;33m🔍 Most Complex Files (by class count):\033[0m"
for file in $(find . -name "*.py" -type f -not -path "*/\.*" | head -20); do
    classes=$(rg "^class " "$file" 2>/dev/null | wc -l | tr -d ' ')
    if [ $classes -gt 5 ]; then
        echo "  $classes classes: $(basename "$file")"
    fi
done | sort -rn | head -10
