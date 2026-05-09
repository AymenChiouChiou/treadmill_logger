from bleak import BleakScanner

FTMS_UUID = "00001826-0000-1000-8000-00805f9b34fb"


async def scan_ftms_devices():

    print("Scanning BLE FTMS devices...\n")

    devices = await BleakScanner.discover(timeout=5.0)

    ftms_devices = []

    for d in devices:

        uuids = d.metadata.get("uuids", [])

        if uuids and FTMS_UUID.lower() in [u.lower() for u in uuids]:

            ftms_devices.append(d)

            print("FTMS device found:")
            print(f"Name    : {d.name}")
            print(f"Address : {d.address}")
            print()

    return ftms_devices