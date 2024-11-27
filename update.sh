#!/bin/bash
set -e

# Global Variables
USER_HOME=$(eval echo ~"$USER")
API_URL="http://127.0.0.1:8880/get_os_version"
VERSION_FILE="$USER_HOME/magnetox-os-update/version.txt"
QT_PACKAGES="qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools libqt5serialport5 libqt5serialport5-dev"
KLIPPERSCREEN_REPO="https://github.com/KlipperScreen/KlipperScreen"
KLIPPERSCREEN_COMMIT="a7b8c4c"
AUTO_UUID_DIR="$USER_HOME/auto-uuid"
PRINTER_DATA_CONFIG="$USER_HOME/printer_data/config"
KLIPPERSCREEN_PANELS="$USER_HOME/KlipperScreen/panels"

# Function to update OS and related packages
update_os() {
    echo "Starting OS update process..."

    if [ -z "$USER_HOME" ]; then
        echo "Error: Could not determine user home directory. Exiting."
        exit 1
    fi

    echo "Updating OS to the latest version..."

    # Install Qt development packages
    echo "Installing Qt development packages..."
    echo 'armbian' | sudo apt-get update -y
    echo 'armbian' | sudo apt-get install -y "$QT_PACKAGES"
    echo "Qt development packages installed successfully."

    # Update KlipperScreen
    echo "Updating KlipperScreen..."
    echo 'armbian' | sudo service KlipperScreen stop

    KLIPPERSCREEN_ENV="$USER_HOME/.KlipperScreen-env/bin"
    "$KLIPPERSCREEN_ENV"/pip3 install sdbus psutil sdbus_networkmanager

    mv "$USER_HOME/KlipperScreen" "$USER_HOME/KlipperScreen-backup" || true
    git clone --depth 1 $KLIPPERSCREEN_REPO "$USER_HOME/KlipperScreen"
    cd "$USER_HOME/KlipperScreen"
    git checkout $KLIPPERSCREEN_COMMIT
    echo "KlipperScreen updated successfully."

    # Copy necessary files
    echo "Copying necessary files..."
    cd "$USER_HOME/magnetox-os-update"
    cp -r auto-uuid/* "$AUTO_UUID_DIR/"
    chmod +x "$AUTO_UUID_DIR/"*.sh
    chmod +x "$AUTO_UUID_DIR/MagnetoWifiHelper"
    chmod +x "$AUTO_UUID_DIR/Magmotor"
    cp -r config/* "$PRINTER_DATA_CONFIG/"
    cp config/Line_Purge.cfg "$PRINTER_DATA_CONFIG/KAMP/"
    cp -r KlipperScreen/* "$KLIPPERSCREEN_PANELS/"
    echo "Files copied successfully."

    echo "Synchronizing filesystem..."
    echo 'armbian' | sudo sync

    echo "OS and applications have been updated successfully. Rebooting now..."
    echo 'armbian' | sudo reboot
}

# Function to compare versions
compare_versions() {
    local version_from_url=$1
    local version_from_file=$2

    if [ "$version_from_url" != "$version_from_file" ]; then
        echo "New version available. Updating..."
        update_os
    else
        echo "No new version available. Exiting."
    fi
}

# Get current version from the API
echo "Checking current OS version..."
current_version=$(curl -s $API_URL | jq -r '.version')
if [ -z "$current_version" ]; then
    echo "Error: Unable to fetch current version from the URL. Exiting."
    exit 1
fi
echo "Current version from URL: $current_version"

# Get version from the local file
file_version=$(cat "$VERSION_FILE")
if [ -z "$file_version" ]; then
    echo "Error: Unable to fetch version from file. Exiting."
    exit 1
fi
echo "Version from file: $file_version"

# Extract version numbers
version_from_url=$(echo "$current_version" | grep -o 'v[0-9]*\.[0-9]*\.[0-9]*')
version_from_file=$(echo "$file_version" | grep -o 'v[0-9]*\.[0-9]*\.[0-9]*')

# Compare versions and update if necessary
compare_versions "$version_from_url" "$version_from_file"
