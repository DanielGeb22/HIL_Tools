import can, cantools, time

dbc = cantools.database.load_file("10.03.25_LC_Main.dbc")
bus = can.interface.Bus()

#### Read safe MCM parameter address ####

# Send A = 0xC1: MCM_Read_Write_Param_Command with Read_Write_Command = 0 and address set
msgA = dbc.get_message_by_name("MCM_Read_Write_Param_Command")
payload = msgA.encode({
    "MCM_Param_Address_Command": 0x0123,
    "MCM_Read_Write_Command": 0,
    "MCM_Data_Command": 0
})

bus.send(can.Message(arbitration_id=msgA.frame_id, data=payload, is_extended_id=False))


# Receive B = 0xC2: MCM_Read_Write_Param_Response with the same address and a valid Data_Response
deadline = time.time() + 0.2
while time.time() < deadline:
    rx = bus.recv(0.02)
    if not rx or rx.arbitration_id != dbc.get_message_by_name("MCM_Read_Write_Param_Response").frame_id:
        continue
    msgB = dbc.get_message_by_name("MCM_Read_Write_Param_Response")
    signals = msgB.decode(bytes(rx.data))
    print("Response:", signals)

    assert signals["MCM_Param_Address_Response"] == 0x0123

    break