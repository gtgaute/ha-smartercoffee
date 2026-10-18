#!/usr/bin/env python3
"""Put a Smarter Coffee (1st gen) on your Wi-Fi without the app.

1. Reset Wi-Fi on the machine: hold the top left (start) button until the
   display shows "WIFI reset", then unplug and plug it back in.
2. Connect your computer to the machine's own network "Smarter Coffee:c1".
3. Run this script. It lists the networks the machine can see, then asks for
   the network name and password.

Protocol (from iBrew):
  0d 7e            scan, answered by 0e "SSID,-dBm}..." 7e
  05 <ssid> 7e     set network name, answered by 03 00 7e
  07 <password> 7e set password, answered by 03 00 7e
  0c 7e            join

Send one message at a time: the machine only reads the first message in a
packet, and waits too long between messages make the join fail.
"""

import getpass
import socket
import sys
import time

HOST = "192.168.4.1"
PORT = 2081
TAIL = 0x7E


def read_for(sock, seconds):
    sock.settimeout(0.5)
    data = b""
    end = time.time() + seconds
    while time.time() < end:
        try:
            chunk = sock.recv(1024)
            if not chunk:
                break
            data += chunk
        except socket.timeout:
            pass
    return data


def wait_ack(sock, seconds):
    """Return the result byte of the first 03 xx 7e, or None."""
    sock.settimeout(0.2)
    buf = b""
    end = time.time() + seconds
    while time.time() < end:
        try:
            buf += sock.recv(1024)
        except socket.timeout:
            continue
        i = buf.find(b"\x03")
        while i >= 0:
            if i + 2 < len(buf) and buf[i + 2] == TAIL:
                return buf[i + 1]
            i = buf.find(b"\x03", i + 1)
    return None


def main():
    print(f"Connecting to {HOST}:{PORT} ...")
    try:
        sock = socket.create_connection((HOST, PORT), timeout=5)
    except OSError as e:
        sys.exit(f"Could not connect: {e}\nIs this computer on the 'Smarter Coffee:c1' network?")

    with sock:
        print("Machine status:", read_for(sock, 1.5).hex(" ") or "(none)")

        sock.sendall(bytes([0x0D, TAIL]))
        raw = read_for(sock, 6)
        start = raw.find(b"\x0e")
        if start >= 0:
            body = raw[start + 1:].split(bytes([TAIL]))[0].decode("utf-8", "replace")
            print("\nNetworks the machine can see:")
            for entry in filter(None, body.split("}")):
                name, _, dbm = entry.rpartition(",")
                print(f"  {name:32} {dbm} dBm")
        else:
            print("No network list:", raw.hex(" ") or "(empty)")

        ssid = input("\nNetwork name (exactly as above): ").strip()
        password = getpass.getpass("Password: ")
        if not ssid:
            sys.exit("Cancelled.")

        for label, msg in (("Network name", bytes([0x05]) + ssid.encode()),
                           ("Password", bytes([0x07]) + password.encode())):
            read_for(sock, 0.2)
            sock.sendall(msg + bytes([TAIL]))
            reply = wait_ack(sock, 2)
            if reply is None:
                sys.exit(f"{label}: no acknowledgement. Try again.")
            if reply != 0x00:
                sys.exit(f"{label}: machine answered error 0x{reply:02x}.")
            print(f"{label}: OK")
        sock.sendall(bytes([0x0C, TAIL]))
        print("Join: sent. Reply:", read_for(sock, 3).hex(" ") or "(none)")

    print("\nThe machine beeps when it has joined. Switch this computer back to your normal Wi-Fi.")


if __name__ == "__main__":
    main()
