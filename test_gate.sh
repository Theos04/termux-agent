#!/bin/bash

USER_ID="19ccf419-6056-4fe6-8a47-682357b35dce"
REQ_PATH="/api/gw/pages/HotelsBookingForm"
BASE_URL="https://www.agoda.com/api/gw/pages/HotelsBookingForm?"
PAYLOAD='{"url":"","rawAttributionData":"","context":{}}'

run_test () {
  local label="$1"
  local ts="$2"
  local uid="$3"
  local meta
  meta=$(echo -n "${ts}|${uid}|${REQ_PATH}" | base64 -w 0)
  echo "=== $label ==="
  echo "x-gate-meta: $meta"
  curl -s -X POST "$BASE_URL" \
    -H "Content-Type: text/plain" \
    -H "x-gate-meta: $meta" \
    -d "$PAYLOAD" \
    -w "\nHTTP Status: %{http_code}\n"
  echo ""
}

run_test "TEST 1: current timestamp"    "1785834440074" "$USER_ID"
run_test "TEST 2: 30 days old"          "1783242440074" "$USER_ID"
run_test "TEST 3: 1 year old"           "1754298440074" "$USER_ID"
run_test "TEST 4: 1 year in future"     "1817370440074" "$USER_ID"
run_test "TEST 7: different userId"     "1785834440074" "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

echo "=== TEST 5: invalid base64 ==="
curl -s -X POST "$BASE_URL" \
  -H "Content-Type: text/plain" \
  -H "x-gate-meta: notbase64atall" \
  -d "$PAYLOAD" \
  -w "\nHTTP Status: %{http_code}\n"
echo ""

echo "=== TEST 6: missing header ==="
curl -s -X POST "$BASE_URL" \
  -H "Content-Type: text/plain" \
  -d "$PAYLOAD" \
  -w "\nHTTP Status: %{http_code}\n"
echo ""
