import serial, time, sys
port = sys.argv[1] if len(sys.argv) > 1 else '/dev/cu.usbmodem1101'
s = serial.Serial(port, 115200, timeout=1)
deadline = time.time() + 20
while time.time() < deadline:
    line = s.readline().decode('utf-8', errors='replace').strip()
    if line:
        print(line, flush=True)
s.close()
