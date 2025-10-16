import can

bus = can.interface.Bus()

while True:
    msg = bus.recv(1.0)
    if msg:
        print(hex(msg.arbitration_id), msg.dlc, msg.data)