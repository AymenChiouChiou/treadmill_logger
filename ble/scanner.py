from bleak import BleakScanner
from bleak.backends.scanner import AdvertisementData

FTMS_UUID = "00001826-0000-1000-8000-00805f9b34fb"


async def scan_ftms_devices():

    print("Scanning BLE FTMS devices...\n")

    ftms_devices = []

    # discover() with return_adv=True gives us AdvertisementData
    # which has service_uuids -- works on bleak 0.19+
    devices_and_adv = await BleakScanner.discover(
        timeout=5.0,
        return_adv=True,
    )

    for address, (device, adv) in devices_and_adv.items():

        uuids = [u.lower() for u in (adv.service_uuids or [])]

        if FTMS_UUID.lower() in uuids:

            ftms_devices.append(device)

            print("FTMS device found:")
            print(f"Name    : {device.name}")
            print(f"Address : {device.address}")
            print()

    if not ftms_devices:
        print("No FTMS treadmill found.")

    return ftms_devices