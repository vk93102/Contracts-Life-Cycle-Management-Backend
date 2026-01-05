#!/bin/bash

# CLM Backend Server Management Script

BACKEND_DIR="/Users/vishaljha/Desktop/CLM/backend"
PORT=8888

function start_server() {
    echo "Starting CLM Backend server on port $PORT..."
    cd "$BACKEND_DIR"
    source venv/bin/activate
    python manage.py runserver $PORT
}

function stop_server() {
    echo "Stopping server..."
    pkill -f "manage.py runserver"
    echo "Server stopped."
}

function restart_server() {
    stop_server
    sleep 2
    start_server
}

function status() {
    if pgrep -f "manage.py runserver" > /dev/null; then
        echo "Server is running"
        ps aux | grep "manage.py runserver" | grep -v grep
    else
        echo "Server is not running"
    fi
}

function test_endpoints() {
    cd "$BACKEND_DIR"
    ./test_all_endpoints.sh
}

function test_e2e() {
    cd "$BACKEND_DIR"
    ./test_e2e.sh
}

function generate_token() {
    cd "$BACKEND_DIR"
    source venv/bin/activate
    python manage.py generate_test_token
}

function show_help() {
    echo "CLM Backend Server Management"
    echo ""
    echo "Usage: ./server.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start       Start the server"
    echo "  stop        Stop the server"
    echo "  restart     Restart the server"
    echo "  status      Check server status"
    echo "  test        Run endpoint tests"
    echo "  e2e         Run end-to-end tests"
    echo "  token       Generate test JWT token"
    echo "  help        Show this help message"
}

# Main
case "$1" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        restart_server
        ;;
    status)
        status
        ;;
    test)
        test_endpoints
        ;;
    e2e)
        test_e2e
        ;;
    token)
        generate_token
        ;;
    help|*)
        show_help
        ;;
esac
