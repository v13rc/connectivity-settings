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
apt install -y ufw fail2ban htop
[ $? -eq 0 ] && echo -e "${GREEN}Success install packages${NC}" || echo -e "${RED}Failed install packages${NC}"

#Net configuration
ufw allow ssh/tcp
ufw limit ssh/tcp
ufw --force enable
[ $? -eq 0 ] && echo -e "${GREEN}Success firewall configuration${NC}" || echo -e "${RED}Failed firewall configuration${NC}"

#Install fail2ban
echo -e "[sshd]\nenabled = true\nport = 22\nfilter = sshd\nlogpath = /var/log/auth.log\nmaxretry = 3" > "/etc/fail2ban/jail.local"
systemctl restart fail2ban
systemctl enable fail2ban
[ $? -eq 0 ] && echo -e "${GREEN}Success fail2ban configuration${NC}" || echo -e "${RED}Failed fail2ban configuration${NC}"
