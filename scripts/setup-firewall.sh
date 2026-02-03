#!/bin/bash
# Gobby Firewall Setup for macOS
# Allows access only from localhost and Tailscale

set -e

echo "Setting up Gobby firewall rules..."

# Create rules file
sudo mkdir -p /etc/pf.anchors
sudo tee /etc/pf.anchors/gobby > /dev/null << 'EOF'
# Gobby Firewall Rules
# Ports: 60887 (HTTP API), 60888 (WebSocket), 5173 (Vite dev server)

# Allow localhost access
pass in quick on lo0 proto tcp from any to any port {5173, 60887, 60888}

# Allow Tailscale subnet (100.64.0.0/10 covers all Tailscale IPs)
pass in quick proto tcp from 100.64.0.0/10 to any port {5173, 60887, 60888}

# Block all other access to Gobby ports
block in quick proto tcp from any to any port {5173, 60887, 60888}
EOF

echo "Created /etc/pf.anchors/gobby"

# Add anchor to pf.conf if not already present
if ! grep -q 'anchor "gobby"' /etc/pf.conf 2>/dev/null; then
    echo "" | sudo tee -a /etc/pf.conf
    echo '# Gobby firewall rules' | sudo tee -a /etc/pf.conf
    echo 'anchor "gobby"' | sudo tee -a /etc/pf.conf
    echo 'load anchor "gobby" from "/etc/pf.anchors/gobby"' | sudo tee -a /etc/pf.conf
    echo "Added anchor to /etc/pf.conf"
else
    echo "Anchor already in /etc/pf.conf"
fi

# Load the rules now
if ! sudo pfctl -ef /etc/pf.conf 2>&1; then
    echo "pfctl -ef failed, trying without -e flag..." >&2
    if ! sudo pfctl -f /etc/pf.conf 2>&1; then
        echo "Error: Failed to load firewall rules" >&2
        exit 1
    fi
fi

echo ""
echo "Firewall configured! Rules will persist across reboots."
echo ""
echo "To verify:"
echo "  sudo pfctl -sr | grep -A5 'anchor \"gobby\"'"
echo ""
echo "To disable temporarily:"
echo "  sudo pfctl -d"
echo ""
echo "To re-enable:"
echo "  sudo pfctl -ef /etc/pf.conf"
