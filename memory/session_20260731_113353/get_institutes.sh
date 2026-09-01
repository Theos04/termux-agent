#!/bin/bash
echo "=== LIST OF INSTITUTES ==="
echo "=========================="
cat dom_trees/dom_113400_702491.json | jq -r '.. | .nodeValue? // empty' 2>/dev/null | \
  grep -E "Institute|College|University|Academy|School|Management|Research" | \
  grep -v "Select\|Option\|Form\|Selected\|Status\|autonomy\|minority\|District\|Sort\|Name\|TFWS\|types\|list\|Department" | \
  grep -E "^[A-Z]" | \
  sort -u | \
  nl
