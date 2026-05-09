import asyncio

from ble.scanner import scan_ftms_devices
from ble.ftms_client import FTMSClient


async def main():

    devices = await scan_ftms_devices()

    if not devices:
        print("No treadmill found.")
        return

    treadmill = devices[0]

    client = FTMSClient(treadmill.address)

    await client.run()


if __name__ == "__main__":
    asyncio.run(main())