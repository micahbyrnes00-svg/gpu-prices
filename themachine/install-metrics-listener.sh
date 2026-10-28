#!/bin/bash
# Dedicated Pi-only collector. Does not modify or restart ordinary SSH.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run this installer with sudo.'; exit 1; }
[ "$(hostname)" = themachine ]
id micahbyrnes >/dev/null
test -s /home/micahbyrnes/.local/lib/picommand/metrics.py
test -s /etc/ssh/ssh_host_ed25519_key
if [ -e /etc/ssh/orbit-metrics.conf ]; then
    echo 'STOP: an Orbit listener configuration already exists; inspect it first.'
    exit 1
fi
install -d -m 755 /etc/orbit-metrics
cat > /etc/orbit-metrics/authorized_keys <<'EOF'
restrict,from="100.79.60.69",command="/usr/bin/python3 /home/micahbyrnes/.local/lib/picommand/metrics.py" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAID9A/uaBoaFSdJXI61gwUKx07kk9Nor4XN38kmE+Gkn0 orbit-readonly-themachine
EOF
chmod 644 /etc/orbit-metrics/authorized_keys
cat > /etc/ssh/orbit-metrics.conf <<'EOF'
Port 2222
ListenAddress 100.125.132.108
HostKey /etc/ssh/ssh_host_ed25519_key
PidFile /run/orbit-metrics-sshd.pid
AuthorizedKeysFile /etc/orbit-metrics/authorized_keys
AllowUsers micahbyrnes
PubkeyAuthentication yes
AuthenticationMethods publickey
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
UsePAM yes
PermitTTY no
DisableForwarding yes
PermitTunnel no
PermitUserEnvironment no
PermitUserRC no
ForceCommand /usr/bin/python3 /home/micahbyrnes/.local/lib/picommand/metrics.py
MaxAuthTries 2
MaxSessions 1
LoginGraceTime 15
LogLevel VERBOSE
EOF
install -d -m 755 /run/sshd
/usr/sbin/sshd -t -f /etc/ssh/orbit-metrics.conf
cat > /etc/systemd/system/orbit-metrics-ssh.service <<'EOF'
[Unit]
Description=Orbit Pi-only read-only metrics SSH
After=network-online.target tailscaled.service
Wants=network-online.target tailscaled.service

[Service]
Type=simple
ExecStartPre=/usr/bin/install -d -m 755 /run/sshd
ExecStartPre=/usr/sbin/sshd -t -f /etc/ssh/orbit-metrics.conf
ExecStart=/usr/sbin/sshd -D -e -f /etc/ssh/orbit-metrics.conf
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now orbit-metrics-ssh.service
systemctl is-active orbit-metrics-ssh.service
ss -ltn 'sport = :2222'
echo 'METRICS LISTENER READY — ordinary SSH and Tailscale SSH unchanged'
