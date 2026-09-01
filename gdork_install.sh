#!/bin/bash
# install.sh - Installation script for gdork

echo "Installing GDORK - Google Dorking CLI Tool"

# Install Python dependencies
pip install -r requirements.txt

# Make the script executable
chmod +x gdork.py

# Create alias (optional)
if [ -f ~/.bashrc ]; then
    echo "alias gdork='python3 $(pwd)/gdork.py'" >> ~/.bashrc
    echo "Alias created! Run 'source ~/.bashrc' to use it."
fi

if [ -f ~/.zshrc ]; then
    echo "alias gdork='python3 $(pwd)/gdork.py'" >> ~/.zshrc
    echo "Alias created! Run 'source ~/.zshrc' to use it."
fi

echo "Installation complete!"
echo "Usage: gdork [domain] [options]"
