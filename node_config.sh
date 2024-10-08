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
ufw allow 22/tcp
ufw allow 8006/tcp
ufw limit 22/tcp
sudo ufw route allow in on vmbr1 out on vmbr0
ufw --force enable
[ $? -eq 0 ] && echo -e "${GREEN}Success firewall configuration${NC}" || echo -e "${RED}Failed firewall configuration${NC}"

#Swap file 8G
fallocate -l 8G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
if [ $? -eq 0 ]; then
echo -e "${GREEN}Success swap file creation${NC}"
echo -e '/swapfile\tnone\tswap\tsw\t0\t0' >> /etc/fstab
[ $? -eq 0 ] && echo -e "${GREEN}Success append /etc/fstab${NC}" || echo -e "${RED}Failed append /etc/fstab${NC}"
else
echo -e "${RED}Failed swap file creation${NC}"
fi

#Install fail2ban
echo -e "[sshd]\nenabled = true\nport = 22\nfilter = sshd\nlogpath = /var/log/auth.log\nmaxretry = 3" > "/etc/fail2ban/jail.local"
systemctl restart fail2ban
systemctl enable fail2ban
[ $? -eq 0 ] && echo -e "${GREEN}Success fail2ban configuration${NC}" || echo -e "${RED}Failed fail2ban configuration${NC}"
