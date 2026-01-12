#!/bin/bash

# Test Password Reset Flow with OTP Verification

BASE_URL="http://127.0.0.1:8000"
TIMESTAMP=$(date +%s)
EMAIL="test_forgot_${TIMESTAMP}@example.com"
PASSWORD="OldPassword123!"
NEW_PASSWORD="NewPassword456!"
FULL_NAME="Forget Password Test User"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Password Reset Flow with OTP Email Verification        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Register User
echo -e "${YELLOW}Step 1: Register new user${NC}"
echo "Email: $EMAIL"

REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register/" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"$PASSWORD\",
    \"full_name\": \"$FULL_NAME\"
  }")

if echo "$REGISTER_RESPONSE" | grep -q "access"; then
  echo -e "${GREEN}✅ User registered successfully${NC}"
  USER_ID=$(echo "$REGISTER_RESPONSE" | grep -o '"user_id":"[^"]*"' | cut -d'"' -f4 | head -1)
  echo "   User ID: $USER_ID"
else
  echo -e "${RED}❌ Registration failed${NC}"
  echo "   Response: $REGISTER_RESPONSE"
  exit 1
fi

echo ""

# Step 2: Request Password Reset (Send OTP)
echo -e "${YELLOW}Step 2: Request password reset (OTP sent to email)${NC}"

FORGOT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/forgot-password/" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\"
  }")

if echo "$FORGOT_RESPONSE" | grep -q "OTP\|Reset"; then
  echo -e "${GREEN}✅ Password reset OTP request successful${NC}"
  echo "   Response: $(echo $FORGOT_RESPONSE | grep -o '"message":"[^"]*"' | cut -d'"' -f4)"
else
  echo -e "${RED}❌ Password reset request failed${NC}"
  echo "   Response: $FORGOT_RESPONSE"
  exit 1
fi

echo ""

# Step 3: Get the actual OTP from the database (for testing)
echo -e "${YELLOW}Step 3: Get OTP from database for testing${NC}"

OTP=$(sqlite3 /tmp/db.sqlite3 "SELECT password_reset_otp FROM authentication_user WHERE email='$EMAIL' LIMIT 1;" 2>/dev/null)

if [ -z "$OTP" ]; then
  echo -e "${YELLOW}⚠️  Could not retrieve OTP from database${NC}"
  echo "   Using dummy OTP for demonstration..."
  OTP="000000"
else
  echo -e "${GREEN}✅ Retrieved OTP: $OTP${NC}"
fi

echo ""

# Step 4: Verify OTP
echo -e "${YELLOW}Step 4: Verify password reset OTP${NC}"

VERIFY_OTP_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/verify-password-reset-otp/" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"otp\": \"$OTP\"
  }")

if echo "$VERIFY_OTP_RESPONSE" | grep -q "verified\|OTP verified"; then
  echo -e "${GREEN}✅ OTP verification successful${NC}"
  echo "   Response: $(echo $VERIFY_OTP_RESPONSE | grep -o '"message":"[^"]*"' | cut -d'"' -f4)"
else
  echo -e "${RED}❌ OTP verification failed${NC}"
  echo "   Response: $VERIFY_OTP_RESPONSE"
  echo "   (This is expected if OTP has expired - continue to step 5)"
fi

echo ""

# Step 5: Reset Password with OTP
echo -e "${YELLOW}Step 5: Reset password with verified OTP${NC}"

RESET_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/reset-password/" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"otp\": \"$OTP\",
    \"password\": \"$NEW_PASSWORD\"
  }")

if echo "$RESET_RESPONSE" | grep -q "Password reset\|password reset"; then
  echo -e "${GREEN}✅ Password reset successful${NC}"
  echo "   Response: $(echo $RESET_RESPONSE | grep -o '"message":"[^"]*"' | cut -d'"' -f4)"
else
  echo -e "${RED}❌ Password reset failed${NC}"
  echo "   Response: $RESET_RESPONSE"
fi

echo ""

# Step 6: Verify New Password Works
echo -e "${YELLOW}Step 6: Verify login with new password${NC}"

LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"$NEW_PASSWORD\"
  }")

if echo "$LOGIN_RESPONSE" | grep -q "access"; then
  echo -e "${GREEN}✅ Login with new password successful${NC}"
  NEW_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access":"[^"]*"' | cut -d'"' -f4 | head -1)
  echo "   New Token: ${NEW_TOKEN:0:30}..."
else
  echo -e "${RED}❌ Login with new password failed${NC}"
  echo "   Response: $LOGIN_RESPONSE"
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║             Password Reset Flow Complete                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
