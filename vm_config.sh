#!/bin/bash
RED='\e[0;31m'
GREEN='\e[0;32m'
BLUE='\e[1;34m'
NC='\e[0m' # No Color

username=$(whoami)

#Update and upgrade
apt update && sudo apt upgrade -y
[ $? -eq 0 ] && echo -e "${GREEN}Success update and upgrade${NC}" || echo -e "${RED}Failed to update and upgrade${NC}"

#Install packages
apt install -y ufw fail2ban htop nano iputils-ping openvpn jq
[ $? -eq 0 ] && echo -e "${GREEN}Success install packages${NC}" || echo -e "${RED}Failed install packages${NC}"

#Net configuration
ufw allow 1194/udp
ufw allow 1195/udp
ufw allow 1196/udp
ufw allow 443
ufw allow 80
ufw allow 9999
ufw allow 26656
ufw allow ssh/tcp
ufw limit ssh/tcp
ufw --force enable
[ $? -eq 0 ] && echo -e "${GREEN}Success firewall configuration${NC}" || echo -e "${RED}Failed firewall configuration${NC}"

#Install fail2ban
echo -e "[sshd]\nenabled = true\nport = 22\nfilter = sshd\nlogpath = /var/log/auth.log\nmaxretry = 3" > "/etc/fail2ban/jail.local"
systemctl restart fail2ban
systemctl enable fail2ban
[ $? -eq 0 ] && echo -e "${GREEN}Success fail2ban configuration${NC}" || echo -e "${RED}Failed fail2ban configuration${NC}"

# SSH

# Check if username is provided
if [ -z "$username" ]; then
    echo -e "${RED}Error: No username provided.${NC}"
    exit 1
fi

# Backup the original sshd_config file
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

# Use sed to update the configuration
sed -i -E "
  s/^#?PermitRootLogin\s+yes/PermitRootLogin no/;
  s/^#?PermitRootLogin\s+prohibit-password/PermitRootLogin no/;
  /AllowUsers/!b;
  /AllowUsers/ s/$/ $username/;
  T
  s/^AllowUsers.*$/AllowUsers $username/
" /etc/ssh/sshd_config

# Check if sed succeeded
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Success: SSHD configuration updated.${NC}"
else
    echo -e "${RED}Failed: SSHD configuration update failed.${NC}"
    exit 1
fi

# Restart the SSH service
systemctl restart ssh

# Check if SSH service restarted successfully
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Success: SSH service restarted successfully.${NC}"
else
    echo -e "${RED}Failed: Could not restart SSH service.${NC}"
fi

#Reboot now
echo -e "${BLUE}Please reboot now${NC}"
