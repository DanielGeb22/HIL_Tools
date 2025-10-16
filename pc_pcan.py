import can

try:
    bus = can.interface.Bus()
    print("OK:", bus is not None)

finally:
    bus.shutdown()