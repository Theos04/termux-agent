#!/bin/bash

# Original values from your transcript
USER_ID="19ccf419-6056-4fe6-8a47-682357b35dce"
PATH="/api/gw/pages/HotelsBookingForm"
BASE_URL="https://www.agoda.com/api/gw/pages/HotelsBookingForm?"
PAYLOAD='{"url":"","rawAttributionData":"","context":{}}'

echo "=== TEST 1: Current timestamp (baseline) ==="
CURRENT_TS="1785834440074"
META=$(echo -n "$CURRENT_TS|$USER_ID|$PATH" | base64 -w 0)
echo "x-gate-meta: $META"
curl -X POST "$BASE_URL" \
  -H "Content-Type: text/plain" \
  -H "x-gate-meta: $META" \
  -d "$PAYLOAD" \
  -s -w "\nHTTP Status: %{http_code}\n" \
  -o /tmp/response_current.txt
cat /tmp/response_current.txt
echo ""

echo "=== TEST 2: 30 days old timestamp ==="
OLD_TS="1783242440074"
META=$(echo -n "$OLD_TS|$USER_ID|$PATH" | base64 -w 0)
echo "x-gate-meta: $META"
curl -X POST "$BASE_URL" \
  -H "Content-Type: text/plain" \
  -H "x-gate-meta: $META" \
  -d "$PAYLOAD" \
  -s -w "\nHTTP Status: %{http_code}\n" \
  -o /tmp/response_old.txt
cat /tmp/response_old.txt
echo ""

echo "=== TEST 3: 1 year old timestamp ==="
YEAR_OLD_TS="1754298440074"
META=$(echo -n "$YEAR_OLD_TS|$USER_ID|$PATH" | base64 -w 0)
echo "x-gate-meta: $META"
curl -X POST "$BASE_URL" \
  -H "Content-Type: text/plain" \
  -H "x-gate-meta: $META" \
  -d "$PAYLOAD" \
  -s -w "\nHTTP Status: %{http_code}\n" \
  -o /tmp/response_year_old.txt
cat /tmp/response_year_old.txt
echo ""

echo "=== TEST 4: Future timestamp (1 year ahead) ==="
FUTURE_TS="1817370440074"
META=$(echo -n "$FUTURE_TS|$USER_ID|$PATH" | base64 -w 0)
echo "x-gate-meta: $META"
curl -X POST "$BASE_URL" \
  -H "Content-Type: text/plain" \
  -H "x-gate-meta: $META" \
  -d "$PAYLOAD" \
  -s -w "\nHTTP Status: %{http_code}\n" \
  -o /tmp/response_future.txt
cat /tmp/response_future.txt
echo ""

echo "=== TEST 5: Invalid base64 ==="
curl -X POST "$BASE_URL" \
  -H "Content-Type: text/plain" \
  -H "x-gate-meta: notbase64atall" \
  -d "$PAYLOAD" \
  -s -w "\nHTTP Status: %{http_code}\n"
echo ""

echo "=== TEST 6: Missing header ==="
curl -X POST "$BASE_URL" \
  -H "Content-Type: text/plain" \
  -d "$PAYLOAD" \
  -s -w "\nHTTP Status: %{http_code}\n"
echo ""
