import asyncio
import os
import sys


async def main():
    # ── Optional: Garmin Connect integration ────────────────────────────────
    # Set GARMIN_EMAIL and GARMIN_PASSWORD env vars, or edit the values below.
    # If not set, the app still works: saves CSV + FIT locally without HR.
    garmin_client = None

    garmin_email    = os.environ.get("GARMIN_EMAIL")
    garmin_password = os.environ.get("GARMIN_PASSWORD")

    if garmin_email and garmin_password:
        try:
            from garmin.client import GarminClient
            garmin_client = GarminClient(garmin_email, garmin_password)
            garmin_client.login()
            print("Garmin Connect: authenticated\n")
        except Exception as e:
            print(f"Garmin Connect: login failed ({e}) - continuing without HR\n")
    else:
        print("Garmin Connect: no credentials set (GARMIN_EMAIL / GARMIN_PASSWORD)")
        print("Running in treadmill-only mode (CSV + FIT without HR)\n")

    # ── Scan for treadmill ───────────────────────────────────────────────────
    from ble.scanner import scan_ftms_devices
    from ble.ftms_client import FTMSClient

    devices = await scan_ftms_devices()

    if not devices:
        print("No treadmill found.")
        return

    treadmill = devices[0]
    client = FTMSClient(treadmill.address, garmin_client=garmin_client)
    await client.run()


if __name__ == "__main__":
    # Windows requires the ProactorEventLoop for BLE (bleak) + asyncio.to_thread
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())