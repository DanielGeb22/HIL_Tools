import can, time

bus = can.interface.Bus()
msg = can.Message(arbitration_id=0x123, data=[0x01, 0x02, 0x03, 0, 0, 0, 0, 0], is_extended_id=False)

for _ in range(10):
    bus.send(msg)
    time.sleep(0.1)