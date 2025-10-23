import time
import can
import cantools

TX_PERIOD_S = 0.01  # 100 Hz

# Values to inject
MOTOR_RPM = 4000
DC_VOLTAGE = 350.0
DC_CURRENT = 175.0
TEST_DURATION_SECONDS = 5.0

dbc = cantools.database.load_file("10.03.25_LC_Main.dbc")

mcm_rpm = dbc.get_message_by_name("MCM_Motor_Position_Info")
mcm_current = dbc.get_message_by_name("MCM_Current_Info")
mcm_voltage = dbc.get_message_by_name("MCM_Voltage_Info")
pl_status_b = dbc.get_message_by_name("VCU_Power_Limit_Status_BMsg")

bus = can.interface.Bus()

print(f"Injecting RPM={MOTOR_RPM}, Voltage={DC_VOLTAGE}, Current={DC_CURRENT}")
print("Waiting for torque command on 0x512...")

t_end = time.time() + TEST_DURATION_SECONDS
next_tx = 0.0

try:
    while time.time() < t_end:
        now = time.time()
        if now >= next_tx:
            data_pos = mcm_rpm.encode({"MCM_Motor_Speed": int(MOTOR_RPM)})
            data_vol = mcm_voltage.encode({"MCM_DC_Bus_Voltage": float(DC_VOLTAGE)})
            data_cur = mcm_current.encode({"MCM_DC_Bus_Current": float(DC_CURRENT)})

            bus.send(can.Message(arbitration_id=mcm_rpm.frame_id, data=data_pos, is_extended_id=False))
            bus.send(can.Message(arbitration_id=mcm_voltage.frame_id, data=data_vol, is_extended_id=False))
            bus.send(can.Message(arbitration_id=mcm_current.frame_id, data=data_cur, is_extended_id=False))

            next_tx = now + TX_PERIOD_S

        msg = bus.recv(0.001)
        if msg and msg.arbitration_id == pl_status_b.frame_id:
            decoded = pl_status_b.decode(bytes(msg.data))
            torque_nm = decoded.get("VCU_POWERLIMIT_getTorqueCommand_Nm")
            print(f"[0x512] Torque command: {torque_nm:.1f} Nm")

    print("Done.")

finally:
    bus.shutdown()