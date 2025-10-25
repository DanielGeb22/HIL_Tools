import time
import struct
import can
import cantools

# Configuration

WSS_CAN_ID = 0x705
TX_PERIOD_S = 0.02              # 50 Hz WSS update
TEST_DURATION_SECONDS = 5.0     # Run for 5 seconds

# Wheel Speed Sensor Values
FL = 100
FR = 100
RL = 50
RR = 50

def build_payload(fl, fr, rl, rr):
    """
    Pack the wheel speeds into a CAN data payloa (x4 16-bit unsigned integers):
    bytes[0..1]=FL, [2..3]=FR, [4..5]=RL, [6..7]=RR
    """
    return struct.pack(">HHHH", fl, fr, rl, rr)

dbc = cantools.database.load_file("10.22.25_SRE_Main.dbc", strict=False)

lc_msg = dbc.get_message_by_name("VCU_LC_Status_A")
lc_id = lc_msg.frame_id

bus = can.interface.Bus()

print(f"Injecting Wheel Speed: FL={FL}, FR={FR}, RL={RL}, RR={RR}")
print("Waiting for Slip Ratio on 0x50B...")

payload = build_payload(FL, FR, RL, RR)

t_end = time.time() + TEST_DURATION_SECONDS
next_tx = 0.0

try:
    while time.time() < t_end:
        now = time.time()
        if now >= next_tx:
            bus.send(can.Message(arbitration_id=WSS_CAN_ID, data=payload, is_extended_id=False))
            next_tx = now + TX_PERIOD_S

        rx = bus.recv(0.001)
        if rx and rx.arbitration_id == lc_id:
            try:    
                decoded = lc_msg.decode(bytes(rx.data))
                slip_ratio = decoded.get("VCU_LaunchControl_SlipRatioScaled")
                if slip_ratio is not None:
                    print(f"[0x50B] SlipRatioScaled = {slip_ratio}")
            except Exception as e:
                    print("Decode error:", e)

    print("Done.")

finally:
    bus.shutdown()