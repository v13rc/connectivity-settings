#!/bin/bash

# Script to install the latest version of grpcurl on Ubuntu

# Update package list and install curl and jq if not already installed
echo "Updating package list and installing curl and jq..."
sudo apt update
sudo apt install -y curl jq

# Fetch the latest version of grpcurl from the GitHub API
echo "Fetching the latest version of grpcurl..."
LATEST_VERSION=$(curl -s https://api.github.com/repos/fullstorydev/grpcurl/releases/latest | jq -r '.tag_name')

# Detect system architecture
ARCH=$(uname -m)
if [[ "$ARCH" == "x86_64" ]]; then
    ARCH="linux_x86_64"
elif [[ "$ARCH" == "aarch64" ]]; then
    ARCH="linux_arm64"
else
    echo "Unsupported architecture: $ARCH"
    exit 1
fi

# Set download URL
URL="https://github.com/fullstorydev/grpcurl/releases/download/${LATEST_VERSION}/grpcurl_${LATEST_VERSION#v}_${ARCH}.tar.gz"

# Download the grpcurl binary
echo "Downloading grpcurl version $LATEST_VERSION for architecture $ARCH..."
curl -L $URL -o grpcurl.tar.gz

# Extract the tar.gz file
echo "Extracting grpcurl..."
tar -xvf grpcurl.tar.gz

# Move the binary to /usr/local/bin
echo "Installing grpcurl to /usr/local/bin..."
sudo mv grpcurl /usr/local/bin/

# Set execution permissions
sudo chmod +x /usr/local/bin/grpcurl

# Clean up downloaded files
echo "Cleaning up..."
rm grpcurl.tar.gz

# Verify the installation
echo "Verifying installation..."
grpcurl --version && echo "Installation successful!" || echo "Installation failed. Please check the installation steps."
