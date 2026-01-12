BASE_URL="https://clm-backend-at23.onrender.com"
TIMESTAMP=$(date +%s)
EMAIL="test_reg_${TIMESTAMP}@example.com"
PASSWORD="TestPassword123!"
FULL_NAME="Test Registration User"

echo "================================"
echo "Testing User Registration with OTP"
echo "================================"
echo ""

# Test 1: Register User
echo "→ Registering user: $EMAIL"
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register/" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"$PASSWORD\",
    \"full_name\": \"$FULL_NAME\"
  }")

echo "Response: $REGISTER_RESPONSE"
echo ""

# Check if registration successful
if echo "$REGISTER_RESPONSE" | grep -q "access"; then
  echo "✅ Registration successful"
  
  # Extract access token
  ACCESS_TOKEN=$(echo "$REGISTER_RESPONSE" | grep -o '"access":"[^"]*"' | cut -d'"' -f4 | head -1)
  USER_ID=$(echo "$REGISTER_RESPONSE" | grep -o '"user_id":"[^"]*"' | cut -d'"' -f4 | head -1)
  
  echo "   User ID: $USER_ID"
  echo "   Token: ${ACCESS_TOKEN:0:30}..."
  
  # Check for OTP message
  if echo "$REGISTER_RESPONSE" | grep -q "OTP"; then
    echo "✅ OTP sent during registration"
  else
    echo "⚠️  No OTP message in response"
  fi
else
  echo "❌ Registration failed"
  echo "   $REGISTER_RESPONSE"
fi

echo ""
echo "================================"
echo "Check your email for:"
echo "  1. Welcome email"
echo "  2. OTP for email verification"
echo "================================"
