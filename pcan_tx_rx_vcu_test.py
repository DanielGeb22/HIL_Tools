import can, time

bus = can.interface.Bus()
msg = can.Message(arbitration_id=0xC0, data=[0x01, 0x02, 0x03, 0x01, 0x01, 0x01, 0x01, 0x01], is_extended_id=False)

for _ in range(10):
    bus.send(msg)
    print("Message sent")
    time.sleep(0.1)


for i in range(200):
    msg1 = bus.recv(1.0)
    if msg1:
        print(hex(msg1.arbitration_id), msg1.dlc, msg1.data)

# 0x510