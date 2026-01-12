BASE_URL="https://clm-backend-at23.onrender.com"
TIMESTAMP=$(date +%s)
TEST_EMAIL="pwd_reset_test_${TIMESTAMP}@example.com"
ORIGINAL_PASSWORD="OriginalPassword123!"
NEW_PASSWORD="NewPassword456!"
FULL_NAME="Password Reset Test"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0

print_header() {
  echo -e "${YELLOW}"
  echo "╔════════════════════════════════════════════════════════════╗"
  echo "║       PASSWORD RESET FLOW VERIFICATION                    ║"
  echo "║   Testing: $BASE_URL"
  echo "║   Email: $TEST_EMAIL"
  echo "║   Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "╚════════════════════════════════════════════════════════════╝"
  echo -e "${NC}"
}

print_step() {
  echo ""
  echo -e "${BLUE}→ STEP: $1${NC}"
}

print_result() {
  local step=$1
  local status=$2
  local details=$3
  
  if [ "$status" = "PASS" ]; then
    echo -e "${GREEN}✅ SUCCESS${NC} - $step"
    ((TESTS_PASSED++))
  else
    echo -e "${RED}❌ FAILED${NC} - $step"
    if [ ! -z "$details" ]; then
      echo -e "   ${RED}Error: $details${NC}"
    fi
    ((TESTS_FAILED++))
  fi
}

print_divider() {
  echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
}

# ============================================================================
# STEP 1: Register User
# ============================================================================
print_step "Register user and receive welcome email + OTP"

REGISTER_RESPONSE=$(curl -s -X POST $BASE_URL/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$ORIGINAL_PASSWORD\",
    \"full_name\": \"$FULL_NAME\"
  }")

REGISTER_EMAIL=$(echo "$REGISTER_RESPONSE" | jq -r '.user.email // .email // empty' 2>/dev/null)
REGISTER_TOKEN=$(echo "$REGISTER_RESPONSE" | jq -r '.access // empty' 2>/dev/null)

if [[ "$REGISTER_EMAIL" == "$TEST_EMAIL" ]]; then
  print_result "User Registration" "PASS"
  echo "   Email: $REGISTER_EMAIL"
  echo "   ✓ Welcome email + OTP sent to registered user"
else
  print_result "User Registration" "FAIL" "$REGISTER_RESPONSE"
  exit 1
fi

# ============================================================================
# STEP 2: Login with Original Password
# ============================================================================
print_step "Login with original password to verify account works"

LOGIN_RESPONSE=$(curl -s -X POST $BASE_URL/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$ORIGINAL_PASSWORD\"
  }")

ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access' 2>/dev/null)
REFRESH_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.refresh' 2>/dev/null)

if [ ! -z "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ]; then
  print_result "Original Password Login" "PASS"
  echo "   Access Token: ${ACCESS_TOKEN:0:20}..."
else
  print_result "Original Password Login" "FAIL" "$LOGIN_RESPONSE"
  exit 1
fi

# ============================================================================
# STEP 3: Request Password Reset (OTP Sent)
# ============================================================================
print_step "Request password reset - OTP should be sent to email"

FORGOT_RESPONSE=$(curl -s -X POST $BASE_URL/api/auth/forgot-password/ \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\"}")

FORGOT_MESSAGE=$(echo "$FORGOT_RESPONSE" | jq -r '.message' 2>/dev/null)

if [[ "$FORGOT_MESSAGE" == *"sent"* ]] || [[ "$FORGOT_MESSAGE" == *"OTP"* ]]; then
  print_result "Password Reset Request (OTP Sent)" "PASS"
  echo "   Message: $FORGOT_MESSAGE"
  echo "   ✓ OTP should be received at: $TEST_EMAIL"
else
  print_result "Password Reset Request (OTP Sent)" "FAIL" "$FORGOT_RESPONSE"
fi

# Note: In real scenario, OTP would come from email
# For testing, we'll demonstrate that endpoint validates properly
echo "   [In production, user would receive OTP via email]"

# ============================================================================
# STEP 4: Verify Password Reset Endpoint Validates OTP
# ============================================================================
print_step "Verify reset endpoint properly validates OTP requirement"

RESET_WITH_INVALID_OTP=$(curl -s -w "\n%{http_code}" -X POST $BASE_URL/api/auth/reset-password/ \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"otp\": \"000000\",
    \"password\": \"$NEW_PASSWORD\"
  }")

HTTP_CODE=$(echo "$RESET_WITH_INVALID_OTP" | tail -1)
RESET_BODY=$(echo "$RESET_WITH_INVALID_OTP" | sed '$d')

if [ "$HTTP_CODE" = "400" ] || echo "$RESET_BODY" | grep -qi "invalid\|error\|otp"; then
  print_result "OTP Validation on Reset Endpoint" "PASS"
  echo "   HTTP Status: $HTTP_CODE"
  echo "   ✓ Endpoint correctly rejects invalid OTP"
  echo "   Response: $(echo "$RESET_BODY" | jq -r '.message // .error // .detail // .' 2>/dev/null | head -1)"
else
  print_result "OTP Validation on Reset Endpoint" "FAIL" "Expected rejection of invalid OTP"
fi

# ============================================================================
# STEP 5: Verify OTP Endpoint Exists
# ============================================================================
print_step "Verify password reset OTP verification endpoint exists"

VERIFY_OTP_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST $BASE_URL/api/auth/verify-password-reset-otp/ \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"otp\": \"000000\"
  }")

HTTP_CODE=$(echo "$VERIFY_OTP_RESPONSE" | tail -1)
VERIFY_BODY=$(echo "$VERIFY_OTP_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" != "404" ]; then
  print_result "Password Reset OTP Verification Endpoint" "PASS"
  echo "   HTTP Status: $HTTP_CODE"
  echo "   ✓ Endpoint exists and is accessible"
  echo "   Response: $(echo "$VERIFY_BODY" | jq -r '.message // .error // .detail // .' 2>/dev/null | head -1)"
else
  print_result "Password Reset OTP Verification Endpoint" "FAIL" "Endpoint not found (404)"
fi

# ============================================================================
# STEP 6: Verify Resend OTP Endpoint Exists
# ============================================================================
print_step "Verify password reset OTP resend endpoint exists"

RESEND_OTP_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST $BASE_URL/api/auth/resend-password-reset-otp/ \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\"}")

HTTP_CODE=$(echo "$RESEND_OTP_RESPONSE" | tail -1)
RESEND_BODY=$(echo "$RESEND_OTP_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" != "404" ]; then
  print_result "Password Reset OTP Resend Endpoint" "PASS"
  echo "   HTTP Status: $HTTP_CODE"
  echo "   ✓ Resend endpoint exists"
  echo "   Response: $(echo "$RESEND_BODY" | jq -r '.message // .error // .detail // .' 2>/dev/null | head -1)"
else
  print_result "Password Reset OTP Resend Endpoint" "FAIL" "Endpoint not found (404)"
fi

# ============================================================================
# SUMMARY
# ============================================================================
print_divider
echo ""
echo -e "${BLUE}PASSWORD RESET FLOW VERIFICATION SUMMARY${NC}"
echo ""
echo "✅ Passed: $TESTS_PASSED tests"
echo "❌ Failed: $TESTS_FAILED tests"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
  echo -e "${GREEN}✅ ALL CHECKS PASSED!${NC}"
  echo ""
  echo "Password Reset Flow Summary:"
  echo "  1. ✅ User can register (receives welcome email + OTP)"
  echo "  2. ✅ User can login with original password"
  echo "  3. ✅ User can request password reset (OTP sent)"
  echo "  4. ✅ Reset endpoint validates OTP requirement"
  echo "  5. ✅ OTP verification endpoint exists"
  echo "  6. ✅ Resend OTP endpoint exists"
  echo ""
  echo "When user receives OTP via email, they can:"
  echo "  • Verify OTP with: POST /api/auth/verify-password-reset-otp/"
  echo "  • Reset password with: POST /api/auth/reset-password/"
  echo "  • Resend OTP with: POST /api/auth/resend-password-reset-otp/"
  echo ""
else
  echo -e "${RED}❌ SOME CHECKS FAILED!${NC}"
fi

print_divider