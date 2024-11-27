import os
import re
import socket
import subprocess
import shutil
import glob
import serial
import serial.tools.list_ports
from pathlib import Path
from flask import Flask, jsonify, request, Response
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dynamically determine the home directory of the current user
# USER_HOME = Path.home() # Does not work as the mag manager runs under root rights - needed?

# Dynamically determine the home directory based on the script's location
SCRIPT_DIR = Path(__file__).resolve().parent
USER_HOME = SCRIPT_DIR.parents[0]

# All paths use the dynamically determined home directory
VERSION_STR = "magneto-x-mainsailOS-2024-9-1-v1.1.4-mag-x-pre"
CONFIG_PATH = USER_HOME / "printer_data/config/magneto_device.cfg"
BACKUP_PATH = USER_HOME / "printer_data/config/magneto_device.cfg.bak"
OS_UPDATE_PATH = USER_HOME / "magnetox-os-update"
CANBUS_QUERY_SCRIPT = USER_HOME / "klipper/scripts/canbus_query.py"
MAG_MOTOR_CONTROL_DIR = USER_HOME / "auto-uuid"
MAG_MOTOR_CONTROL_FILENAME = "mag_motor_control.sh"
KLIPPY_ENV = USER_HOME / "klippy-env/bin/python"

app = Flask(__name__)
serial_connection = None

def connect_to_serial():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "USB Serial" in port.description:
            try:
                return serial.Serial(port.device, 115200)
            except Exception as e:
                logger.error(f"Failed to connect to serial: {e}")
    return None

@app.route("/get_timezone", methods=["GET"])
def get_timezone():
    try:
        timezone = subprocess.run(
            ["timedatectl", "show"],
            capture_output=True,
            text=True,
            check=True,
        )
        return jsonify({"timezone": timezone.stdout.strip()})
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to retrieve timezone: {e}")
        return jsonify({"error": f"Failed to retrieve timezone: {e}"}), 500

@app.route("/set_timezone", methods=["GET", "POST"])
def set_timezone():
    try:
        new_timezone = request.args.get("timezone")
        if not new_timezone:
            result = subprocess.run(
                ["curl", "--fail", "https://ipapi.co/timezone"],
                capture_output=True,
                text=True,
                check=True,
            )
            new_timezone = result.stdout.strip()

        subprocess.run(
            ["timedatectl", "set-timezone", new_timezone],
            check=True,
        )
        return jsonify({"timezone": new_timezone})
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to set timezone: {e}")
        return jsonify({"error": f"Failed to set timezone: {e}"}), 500

@app.route("/get_os_version", methods=["GET"])
def get_os_version():
    return jsonify({"version": VERSION_STR})

@app.route("/get_git_version", methods=["GET"])
def get_git_version():
    try:
        subprocess.run(
            [
                "git",
                "config",
                "--global",
                "--add",
                "safe.directory",
                str(OS_UPDATE_PATH),
            ],
            check=True,
        )
        branch = subprocess.run(
            ["git", "-C", str(OS_UPDATE_PATH), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        commit = subprocess.run(
            ["git", "-C", str(OS_UPDATE_PATH), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return jsonify({"git_branch": branch, "git_commit": commit})
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to retrieve Git version: {e}")
        return jsonify({"error": f"Failed to retrieve Git version: {e}"}), 500

@app.route("/connect_lm", methods=["GET"])
def connect_esplm():
    global serial_connection
    serial_connection = connect_to_serial()
    if serial_connection is None:
        return jsonify({"error": "No compatible USB serial device found"}), 404
    logger.info(f"Connected to {serial_connection.port}")
    return jsonify({"connected": serial_connection.port})

@app.route("/disconnect_lm", methods=["GET"])
def disconnect_serial():
    global serial_connection
    if serial_connection and serial_connection.is_open:
        serial_connection.close()
        logger.info("Serial connection closed.")
        return jsonify({"info": "Serial connection closed"})
    else:
        logger.info("No open serial connection to close.")
        return jsonify({"info": "No open serial connection to close"})

@app.route("/motor_control", methods=["GET"])
def linear_motor_debug():
    try:
        script_path = str(MAG_MOTOR_CONTROL_DIR / MAG_MOTOR_CONTROL_FILENAME)
        directory_path = str(MAG_MOTOR_CONTROL_DIR)
        
        logger.info(f"Running script: {script_path} with argument: {directory_path}")
        
        result = subprocess.run(
            [script_path, directory_path],
            capture_output=True,
            text=True,
            check=True,
        )
        
        return jsonify(
            {"stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Motor control script error: {e}")
        return jsonify({"error": f"Motor control script error: {e}", "stdout": e.stdout, "stderr": e.stderr}), 500

@app.route("/send_command", methods=["GET"])
def send_command():
    global serial_connection
    if not serial_connection:
        return jsonify({"error": "Serial port not connected"}), 400

    command = request.args.get("command") + "\n"

    if command:
        try:
            serial_connection.write(command.encode())
            return jsonify({"success": "Command sent successfully"})
        except Exception as e:
            logger.error(f"Failed to send command: {e}")
            return jsonify({"error": "Failed to send command"}), 500
    else:
        return jsonify({"error": "Invalid command"}), 400

@app.route("/auto_resize_filesystem", methods=["GET"])
def auto_resize_filesystem():
    try:
        output = run_command("systemctl start orangepi-resize-filesystem.service")
        logger.info("Filesystem resized")
        return jsonify({"success": output})
    except subprocess.CalledProcessError as e:
        logger.error(f"Error occurred while resizing filesystem: {e}")
        return jsonify({"error": f"Error occurred while resizing filesystem: {e}"}), 500

def run_command(command):
    try:
        output = subprocess.check_output(
            command, shell=True, stderr=subprocess.STDOUT
        ).decode("utf-8")
        return output
    except subprocess.CalledProcessError as e:
        return e.output.decode("utf-8")

def extract_uuids(output):
    uuids = re.findall(r"canbus_uuid=(\w+)", output)
    return uuids

def backup_config_file(filename):
    backup_filename = f"{filename}.backup"
    shutil.copy2(filename, backup_filename)

def modify_config_file(filename, uuid):
    with open(filename, "r") as file:
        lines = file.readlines()

    for index, line in enumerate(lines):
        if "canbus_uuid:" in line:
            lines[index] = f"canbus_uuid: {uuid}\n"
            break

    with open(filename, "w") as file:
        file.writelines(lines)
        file.flush()
        os.fsync(file.fileno())

def get_serial_devices():
    devices = glob.glob("/dev/serial/by-id/*")
    return devices

def backup_config():
    shutil.copy2(CONFIG_PATH, BACKUP_PATH)

def update_config_file(device):
    if not device:
        return

    with open(CONFIG_PATH, "r") as file:
        content = file.readlines()

    mcu_section_found = False
    for index, line in enumerate(content):
        if line.strip() == "[mcu]":
            mcu_section_found = True

            while "serial:" not in content[index] and content[index].strip() != "":
                index += 1
            if "serial:" in content[index]:
                content[index] = "serial: {}\n".format(device)
                break

    if not mcu_section_found:
        content.append("\n[mcu]\n")
        content.append("serial: {}\n".format(device))

    with open(CONFIG_PATH, "w") as file:
        file.writelines(content)
        file.flush()
        os.fsync(file.fileno())

@app.route("/get-ip", methods=["GET"])
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Use a non-existent address for the purpose of initialising a connection for the correct IP
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return jsonify({"ip": IP})

@app.route("/get-mcu-uuid", methods=["GET"])
def get_mcu_uuid():
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found at {CONFIG_PATH}")
        return jsonify({"error": "Config file not found"}), 404

    devices = get_serial_devices()
    for device in devices:
        if device.startswith("/dev/serial/by-id/usb-Klipper"):
            return jsonify({"mcu-uuid": device})

    return jsonify({"error": "No MCU UUID found"}), 404

@app.route("/set-mcu-uuid", methods=["GET"])
def set_mcu_uuid():
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found at {CONFIG_PATH}")
        return jsonify({"error": "Config file not found"}), 404

    devices = get_serial_devices()
    for device in devices:
        if device.startswith("/dev/serial/by-id/usb-Klipper"):
            backup_config()
            update_config_file(device)
            return jsonify({"mcu-uuid-success": device})

    return jsonify({"error": "No MCU UUID found"}), 404

@app.route("/set-can-uuid", methods=["GET"])
def set_can_uuid():
    try:
        # Check if the file exists
        if not CONFIG_PATH.exists():
            return jsonify({"error": f"{CONFIG_PATH} not found!"}), 404

        # Perform backups
        backup_config_file(CONFIG_PATH)

        command = f"{KLIPPY_ENV} {CANBUS_QUERY_SCRIPT} can0"
        output = run_command(command)
        uuids = extract_uuids(output)

        # Determine the number of uuids and take the appropriate value
        if len(uuids) >= 1:
            uuid_to_use = uuids[-1]
            modify_config_file(CONFIG_PATH, uuid_to_use)
            return jsonify(
                {"success": "CAN UUID set successfully", "uuid": uuid_to_use}
            )
        else:
            return jsonify(
                {"error": f"Found {len(uuids)} CAN UUIDs, expected at least 1"}
            ), 400
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route("/get-can-uuid", methods=["GET"])
def get_can_uuid():
    command = f"{KLIPPY_ENV} {CANBUS_QUERY_SCRIPT} can0"
    output = run_command(command)
    uuids = extract_uuids(output)

    return jsonify({"can-uuids": uuids})

if __name__ == "__main__":
    serial_connection = connect_to_serial()
    if serial_connection is None:
        logger.info("No device found!")
    else:
        logger.info(f"Connected {serial_connection.port}")
    app.run(host="0.0.0.0", port=8880)
