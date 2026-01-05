#!/bin/bash

# Kill any existing servers
pkill -f "manage.py runserver"
sleep 2

# Go to backend directory
cd /Users/vishaljha/Desktop/CLM/backend

# Activate venv
source venv/bin/activate

# Start server
echo "Starting Django server..."
python manage.py runserver 127.0.0.1:8888 > /tmp/django_server.log 2>&1 &
SERVER_PID=$!

echo "Server PID: $SERVER_PID"

# Wait for server to start
echo "Waiting for server to start..."
sleep 5

# Test endpoints
echo "Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s http://127.0.0.1:8888/api/v1/health/)
echo "Health Response: $HEALTH_RESPONSE"

# Check if server is still running
if ps -p $SERVER_PID > /dev/null; then
   echo "Server is running!"
else
   echo "Server crashed! Check logs:"
   cat /tmp/django_server.log
fi

# Keep server running
wait $SERVER_PID
