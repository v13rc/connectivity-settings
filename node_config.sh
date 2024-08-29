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
ufw default deny incoming
ufw default allow outgoing

ufw allow 22/tcp                      # SSH dostępny z dowolnego miejsca
ufw allow 8006/tcp                    # Proxmox Web GUI
ufw allow 5404/tcp                    # Proxmox Cluster (cman) TCP
ufw allow 5404/udp                    # Proxmox Cluster (cman) UDP
ufw allow 5405/tcp                    # Proxmox Cluster (cman) TCP
ufw allow 5405/udp                    # Proxmox Cluster (cman) UDP
ufw allow 2049/tcp                    # NFS (jeśli używasz)
ufw allow 3260/tcp                    # iSCSI (jeśli używasz)
ufw allow out 53/udp                  # Wychodzące zapytania DNS
ufw allow out 53/tcp                  # Wychodzące zapytania DNS (opcjonalnie)
ufw limit 22/tcp                      # Ograniczenie liczby prób logowania SSH
ufw enable                            # Włączenie UFW
ufw --force enable
[ $? -eq 0 ] && echo -e "${GREEN}Success firewall configuration${NC}" || echo -e "${RED}Failed firewall configuration${NC}"

#Install fail2ban
echo -e "[sshd]\nenabled = true\nport = 22\nfilter = sshd\nlogpath = /var/log/auth.log\nmaxretry = 3" > "/etc/fail2ban/jail.local"
systemctl restart fail2ban
systemctl enable fail2ban
[ $? -eq 0 ] && echo -e "${GREEN}Success fail2ban configuration${NC}" || echo -e "${RED}Failed fail2ban configuration${NC}"
