#!/usr/bin/env bash
# ============================================================
# Customer Service — Complete API Test Script
# Usage:
#   Local Docker : bash test-customer-service.sh
#   Minikube     : bash test-customer-service.sh http://127.0.0.1:61339
# ============================================================

BASE="${1:-http://localhost:8001}/api/v1"
PASS=0; FAIL=0

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

check() {
  local label="$1" expected="$2" actual="$3"
  if echo "$actual" | grep -q "$expected"; then
    echo -e "${GREEN}  PASS${NC} $label"
    ((PASS++))
  else
    echo -e "${RED}  FAIL${NC} $label"
    echo "       expected: $expected"
    echo "       got     : $(echo $actual | head -c 200)"
    ((FAIL++))
  fi
}

section() { echo -e "\n${CYAN}── $1 ──────────────────────────────────────────${NC}"; }

# ============================================================
# SETUP
# ============================================================
section "SETUP"
echo "Base URL : $BASE"
echo ""

# ── Execution Instructions ──────────────────────────────────
# OPTION A – Docker Compose (recommended)
#   cd banking_project
#   docker compose up --build customer-svc customer-db
#   bash customer-service/test-customer-service.sh
#
# OPTION B – Minikube
#   Terminal 1: minikube service customer-svc -n banking --url
#   Terminal 2: bash customer-service/test-customer-service.sh http://127.0.0.1:61339
#
# OPTION C – Local (no Docker)
#   export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost/customer_db"
#   export RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
#   cd customer-service && uvicorn app.main:app --port 8001 --reload
#   bash test-customer-service.sh
# ────────────────────────────────────────────────────────────

# ============================================================
# 1. HEALTH CHECK
# ============================================================
section "1. HEALTH CHECK"

res=$(curl -s "$BASE/health")
echo "Response: $res"
check "service is healthy" "healthy" "$res"

# ============================================================
# 2. CREATE CUSTOMERS
# ============================================================
section "2. CREATE CUSTOMERS"

# 2a. Create customer 1
res=$(curl -s -X POST "$BASE/customers" \
  -H "Content-Type: application/json" \
  -d '{"name":"Priya Sharma","email":"priya.sharma@example.com","phone":"9876543210","kyc_status":"PENDING"}')
echo "Create Customer 1: $res"
check "customer created with name" "Priya Sharma" "$res"
check "kyc_status defaults to PENDING" "PENDING" "$res"

# 2b. Create customer 2
res=$(curl -s -X POST "$BASE/customers" \
  -H "Content-Type: application/json" \
  -d '{"name":"Rohan Das","email":"rohan.das@bankmail.in","phone":"9123456780"}')
echo "Create Customer 2: $res"
check "second customer created" "Rohan Das" "$res"

# 2c. Duplicate email → 409
res=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/customers" \
  -H "Content-Type: application/json" \
  -d '{"name":"Dup User","email":"priya.sharma@example.com","phone":"9000000000"}')
echo "Duplicate email HTTP status: $res"
check "duplicate email returns 409" "409" "$res"

# 2d. Invalid email → 422
res=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/customers" \
  -H "Content-Type: application/json" \
  -d '{"name":"Bad","email":"not-an-email","phone":"9000000000"}')
echo "Invalid email HTTP status: $res"
check "invalid email returns 422" "422" "$res"

# 2e. Short phone → 422
res=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/customers" \
  -H "Content-Type: application/json" \
  -d '{"name":"Bad","email":"ok@example.com","phone":"123"}')
echo "Short phone HTTP status: $res"
check "short phone returns 422" "422" "$res"

# ============================================================
# 3. READ CUSTOMERS
# ============================================================
section "3. READ CUSTOMERS"

# 3a. Get seeded customer by ID
res=$(curl -s "$BASE/customers/1")
echo "Get Customer 1: $res"
check "seeded customer found" "Vivaan Khan" "$res"

# 3b. Get non-existent customer → 404
res=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/customers/9999")
echo "Non-existent customer HTTP status: $res"
check "missing customer returns 404" "404" "$res"

# 3c. List customers (page 1, size 5)
res=$(curl -s "$BASE/customers?page=1&size=5")
echo "List (page=1, size=5): $res"
check "list returns array" "\[" "$res"

# 3d. Filter by PENDING
res=$(curl -s "$BASE/customers?kyc_status=PENDING")
echo "Filter PENDING: $res"
check "pending filter works" "PENDING" "$res"

# 3e. Filter by VERIFIED
res=$(curl -s "$BASE/customers?kyc_status=VERIFIED")
echo "Filter VERIFIED: $res"
check "verified filter works" "VERIFIED" "$res"

# 3f. Filter by REJECTED
res=$(curl -s "$BASE/customers?kyc_status=REJECTED")
echo "Filter REJECTED: $res"
check "rejected filter works" "REJECTED" "$res"

# ============================================================
# 4. UPDATE CUSTOMER
# ============================================================
section "4. UPDATE CUSTOMER"

# 4a. Update name and phone
res=$(curl -s -X PUT "$BASE/customers/1" \
  -H "Content-Type: application/json" \
  -d '{"name":"Vivaan Khan Updated","phone":"9000000099"}')
echo "Update Customer 1: $res"
check "name updated" "Vivaan Khan Updated" "$res"
check "phone updated" "9000000099" "$res"

# 4b. Verify update persisted
res=$(curl -s "$BASE/customers/1")
echo "Verify update: $res"
check "update persisted in DB" "Vivaan Khan Updated" "$res"

# ============================================================
# 5. KYC MANAGEMENT
# ============================================================
section "5. KYC MANAGEMENT"

# 5a. Get KYC status
res=$(curl -s "$BASE/customers/6/kyc")
echo "Get KYC customer 6: $res"
check "kyc status returned" "kyc_status" "$res"

# 5b. Approve KYC (customer 6 is PENDING in seed data)
res=$(curl -s -X PATCH "$BASE/customers/6/kyc" \
  -H "Content-Type: application/json" \
  -d '{"kyc_status":"VERIFIED"}')
echo "Approve KYC customer 6: $res"
check "kyc approved to VERIFIED" "VERIFIED" "$res"

# 5c. Reject KYC (customer 13 is PENDING in seed data)
res=$(curl -s -X PATCH "$BASE/customers/13/kyc" \
  -H "Content-Type: application/json" \
  -d '{"kyc_status":"REJECTED"}')
echo "Reject KYC customer 13: $res"
check "kyc rejected" "REJECTED" "$res"

# 5d. Reset to PENDING
res=$(curl -s -X PATCH "$BASE/customers/13/kyc" \
  -H "Content-Type: application/json" \
  -d '{"kyc_status":"PENDING"}')
echo "Reset KYC customer 13: $res"
check "kyc reset to PENDING" "PENDING" "$res"

# 5e. Invalid KYC value → 422
res=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$BASE/customers/1/kyc" \
  -H "Content-Type: application/json" \
  -d '{"kyc_status":"APPROVED"}')
echo "Invalid KYC value HTTP status: $res"
check "invalid kyc value returns 422" "422" "$res"

# 5f. KYC on non-existent customer → 404
res=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/customers/9999/kyc")
echo "KYC non-existent customer HTTP status: $res"
check "missing customer kyc returns 404" "404" "$res"

# ============================================================
# 6. DELETE CUSTOMER
# ============================================================
section "6. DELETE CUSTOMER"

# 6a. Create a temp customer to delete
tmp=$(curl -s -X POST "$BASE/customers" \
  -H "Content-Type: application/json" \
  -d '{"name":"Temp Delete","email":"temp.delete@example.com","phone":"9111111111"}')
tmp_id=$(echo $tmp | grep -o '"customer_id":[0-9]*' | grep -o '[0-9]*')
echo "Created temp customer ID: $tmp_id"

# 6b. Delete it
res=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/customers/$tmp_id")
echo "Delete temp customer HTTP status: $res"
check "customer deleted returns 204" "204" "$res"

# 6c. Verify deleted
res=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/customers/$tmp_id")
echo "Fetch deleted customer HTTP status: $res"
check "deleted customer returns 404" "404" "$res"

# ============================================================
# 7. METRICS
# ============================================================
section "7. PROMETHEUS METRICS"

res=$(curl -s "http://${BASE#http://*/api/v1}/metrics" 2>/dev/null || curl -s "${BASE%/api/v1}/metrics")
if echo "$res" | grep -q "http_requests_total"; then
  echo -e "${GREEN}  PASS${NC} Prometheus metrics endpoint active"
  ((PASS++))
else
  echo -e "${RED}  FAIL${NC} Prometheus metrics not found"
  ((FAIL++))
fi

# ============================================================
# SUMMARY
# ============================================================
section "RESULTS"
TOTAL=$((PASS + FAIL))
echo -e "  Total : $TOTAL"
echo -e "  ${GREEN}Passed${NC} : $PASS"
echo -e "  ${RED}Failed${NC} : $FAIL"
echo ""
if [ $FAIL -eq 0 ]; then
  echo -e "${GREEN}All tests passed!${NC}"
  exit 0
else
  echo -e "${RED}$FAIL test(s) failed.${NC}"
  exit 1
fi
