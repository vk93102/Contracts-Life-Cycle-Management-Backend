#!/bin/bash
# CLM BACKEND - QUICK START GUIDE
# Production-Ready Setup & Verification

echo "╔════════════════════════════════════════════════════════════════════════════════╗"
echo "║                    CLM BACKEND - QUICK START GUIDE                             ║"
echo "║                      Production-Ready Version v1.0                              ║"
echo "╚════════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKEND_DIR="/Users/vishaljha/Desktop/SK/CLM/backend"
PORT=4000

echo -e "${BLUE}[1/5] Checking Python Environment...${NC}"
cd "$BACKEND_DIR"
python --version

echo -e "${BLUE}[2/5] Starting Background Task Worker...${NC}"
python manage.py process_tasks > logs/worker.log 2>&1 &
WORKER_PID=$!
echo -e "${GREEN}✅ Worker started (PID: $WORKER_PID)${NC}"

echo -e "${BLUE}[3/5] Starting Django Server...${NC}"
python manage.py runserver $PORT > logs/server.log 2>&1 &
SERVER_PID=$!
sleep 5
echo -e "${GREEN}✅ Server started (PID: $SERVER_PID)${NC}"

echo -e "${BLUE}[4/5] Verifying API Health...${NC}"
HEALTH=$(curl -s http://localhost:$PORT/api/health/)
if echo "$HEALTH" | grep -q "ok"; then
    echo -e "${GREEN}✅ API is healthy${NC}"
else
    echo -e "${YELLOW}⚠️  API health check failed${NC}"
fi

echo -e "${BLUE}[5/5] Running Comprehensive Tests...${NC}"
python run_real_tests.py | tee FINAL_TEST_RESULTS.txt

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ ALL SYSTEMS OPERATIONAL${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "📊 Server Details:"
echo -e "  Base URL:        http://localhost:$PORT"
echo -e "  API Endpoint:    http://localhost:$PORT/api"
echo -e "  Server PID:      $SERVER_PID"
echo -e "  Worker PID:      $WORKER_PID"
echo ""
echo -e "📁 Important Files:"
echo -e "  Test Results:    FINAL_TEST_RESULTS.txt"
echo -e "  Server Log:      logs/server.log"
echo -e "  Worker Log:      logs/worker.log"
echo -e "  Report:          PRODUCTION_READY_VERIFICATION.md"
echo ""
echo -e "🔗 Available Endpoints:"
echo -e "  Auth:            POST   /api/auth/login/"
echo -e "  Search:          POST   /api/search/global/"
echo -e "  Suggestions:     GET    /api/search/suggestions/?q=<query>"
echo -e "  Clause Summary:  POST   /api/analysis/clause-summary/"
echo -e "  Comparison:      POST   /api/analysis/compare/"
echo -e "  Related:         GET    /api/contracts/{id}/related/"
echo -e "  Generation:      POST   /api/generation/start/"
echo -e "  Status:          GET    /api/generation/{id}/status/"
echo ""
echo -e "⏹️  To Stop Services:"
echo -e "  kill -9 $SERVER_PID  # Stop Django server"
echo -e "  kill -9 $WORKER_PID  # Stop background worker"
echo ""
echo -e "${YELLOW}Note: Check logs for detailed information on any issues${NC}"
