#!/bin/bash

# Sync Workspace directory to remote server
# Target: user01@192.168.1.65:/home/user01/Workspace

# Configuration
REMOTE_USER="user01"
REMOTE_HOST="192.168.1.65"
REMOTE_PATH="/home/user01/Workspace"
LOCAL_PATH="./Workspace/"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting workspace sync...${NC}"
echo -e "Local path: ${LOCAL_PATH}"
echo -e "Remote target: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}"
echo ""

# Check if local Workspace directory exists
if [ ! -d "${LOCAL_PATH}" ]; then
    echo -e "${RED}Error: Local Workspace directory not found!${NC}"
    echo -e "Expected path: ${LOCAL_PATH}"
    exit 1
fi

# Test SSH connection
echo -e "${YELLOW}Testing SSH connection...${NC}"
ssh -o ConnectTimeout=10 -q "${REMOTE_USER}@${REMOTE_HOST}" exit
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Cannot connect to ${REMOTE_USER}@${REMOTE_HOST}${NC}"
    echo "Please check:"
    echo "  - Network connectivity"
    echo "  - SSH credentials"
    echo "  - Remote host availability"
    exit 1
fi
echo -e "${GREEN}SSH connection successful!${NC}"

# Create remote directory if it doesn't exist
echo -e "${YELLOW}Ensuring remote directory exists...${NC}"
ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_PATH}"

# Sync files using rsync
echo -e "${YELLOW}Syncing files...${NC}"
rsync -avz --progress --delete \
    "${LOCAL_PATH}" \
    "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/"

# Check if sync was successful
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Workspace sync completed successfully!${NC}"
    echo -e "All files have been synchronized to ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}"
else
    echo ""
    echo -e "${RED}✗ Sync failed!${NC}"
    echo "Please check the error messages above and try again."
    exit 1
fi