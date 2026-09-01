#!/bin/bash
# Quick analysis for specific files

TARGET="${1:-cdpv119.py}"

echo -e "\033[0;36m📊 Analyzing: $TARGET\033[0m"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Quick stats
echo -e "\033[0;32m📈 Statistics:\033[0m"
echo "  Classes: $(rg "^class " "$TARGET" 2>/dev/null | wc -l | tr -d ' ')"
echo "  Functions: $(rg "^def " "$TARGET" 2>/dev/null | wc -l | tr -d ' ')"
echo "  Methods: $(rg "^    def " "$TARGET" 2>/dev/null | wc -l | tr -d ' ')"
echo "  Imports: $(rg "^(import|from) " "$TARGET" 2>/dev/null | wc -l | tr -d ' ')"
echo "  Lines: $(cat "$TARGET" 2>/dev/null | wc -l | tr -d ' ')"

# Show classes
echo ""
echo -e "\033[0;34m📋 Classes:\033[0m"
rg "^class " "$TARGET" 2>/dev/null | sed 's/^/  /' || echo "  No classes found"

# Show functions
echo ""
echo -e "\033[0;34m📋 Top-level Functions:\033[0m"
rg "^def " "$TARGET" 2>/dev/null | sed 's/^/  /' || echo "  No top-level functions found"

# Show main entry point
echo ""
echo -e "\033[0;33m🚀 Entry Point:\033[0m"
if grep -q "if __name__" "$TARGET" 2>/dev/null; then
    echo "  ✓ Has main() entry point"
    rg "if __name__" "$TARGET" -A 3 | sed 's/^/  /'
else
    echo "  No main() entry point found"
fi

# Show TODOs
echo ""
echo -e "\033[0;33m📝 TODOs/FIXMEs:\033[0m"
rg "TODO|FIXME|HACK|BUG" "$TARGET" 2>/dev/null | sed 's/^/  /' || echo "  None found"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "\033[0;32m✅ Analysis complete!\033[0m"
