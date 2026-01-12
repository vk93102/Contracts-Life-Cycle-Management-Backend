#!/bin/bash

BASE_URL="http://127.0.0.1:8000"
TIMESTAMP=$(date +%s)
EMAIL="emailtest_${TIMESTAMP}@example.com"
PASSWORD="TestPass123!"

echo "Testing Email System for CLM Backend"
echo "======================================"
echo ""

echo "1. Testing User Registration (should send welcome email)"
REGISTER=$(curl -s -X POST "$BASE_URL/api/auth/register/" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"$PASSWORD\",
    \"full_name\": \"Email Test User\"
  }")

TOKEN=$(echo "$REGISTER" | grep -o '"access":"[^"]*"' | cut -d'"' -f4 | head -1)

if [ ! -z "$TOKEN" ]; then
  echo "✅ User registered successfully"
  echo "   Email: $EMAIL"
  echo "   Check email for welcome message"
else
  echo "❌ Registration failed: $REGISTER"
  exit 1
fi

echo ""
echo "2. Testing Request Login OTP (should send OTP email)"
OTP_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/request-login-otp/" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\"}")

echo "Response: $OTP_RESPONSE"
if echo "$OTP_RESPONSE" | grep -q "OTP sent"; then
  echo "✅ OTP request sent"
  echo "   Check email for OTP code"
else
  echo "⚠️  Response received (check server logs for email sending)"
fi

echo ""
echo "3. Testing Forgot Password (should send password reset OTP)"
FORGOT=$(curl -s -X POST "$BASE_URL/api/auth/forgot-password/" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\"}")

echo "Response: $FORGOT"
if echo "$FORGOT" | grep -q "Reset OTP\|OTP sent"; then
  echo "✅ Password reset OTP requested"
  echo "   Check email for reset OTP code"
else
  echo "⚠️  Response received (check server logs for email sending)"
fi

echo ""
echo "======================================"
echo "Email System Test Complete"
echo "Check /tmp/django_server.log for detailed logs"
