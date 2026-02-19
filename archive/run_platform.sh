#!/bin/bash
# Run the Match Intelligence Backtesting Platform

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}⚽ Starting Clarity Engine - Match Intelligence Platform${NC}"
echo ""

# Check if required dependencies are installed
if ! command -v uvicorn &> /dev/null; then
    echo "Installing FastAPI dependencies..."
    pip install fastapi uvicorn
fi

# Navigate to project root
cd "$(dirname "$0")"

# Start FastAPI backend in background
echo -e "${GREEN}🚀 Starting FastAPI backend on port 8000...${NC}"
uvicorn src.api.main:app --reload --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 2

# Start Vite frontend
echo -e "${GREEN}🎨 Starting Vite frontend on port 5173...${NC}"
cd src/web
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Platform is running!${NC}"
echo ""
echo "   Frontend:  http://localhost:5173"
echo "   Backend:   http://localhost:8000"
echo "   API Docs:  http://localhost:8000/docs"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for Ctrl+C
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
