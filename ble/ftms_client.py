import asyncio

from bleak import BleakClient

from ble.ftms_parser import parse_treadmill_data

from session.workout_detector import WorkoutDetector
from storage.session_buffer import SessionBuffer
from model.sample import Sample

import time

TREADMILL_DATA_UUID = "00002acd-0000-1000-8000-00805f9b34fb"


class FTMSClient:

    def __init__(self, address):

        self.address = address

        self.client = None

        self.connected = False

        self.detector = WorkoutDetector()

        self.buffer = SessionBuffer()

    async def connect(self):

        print(f"Connecting to {self.address}...\n")

        self.client = BleakClient(
            self.address,
            disconnected_callback=self.on_disconnect
        )

        await self.client.connect()

        self.connected = self.client.is_connected

        print("Connected :", self.connected)

    def on_disconnect(self, client):

        print("\nTreadmill disconnected!\n")

        self.connected = False

    async def start_notifications(self):

        print("Starting notify...")

        def notification_handler(sender, data):
            print("NOTIFICATION RECEIVED")

            parsed = parse_treadmill_data(data)

            print(parsed)
            # =========================
            # GET SPEED
            # =========================

            speed = parsed.get("speed_kmh", 0)

            print(f"Speed = {speed}")

            # =========================
            # UPDATE WORKOUT DETECTOR
            # =========================

            event = self.detector.update(speed)

            if self.detector.is_running:
                sample = Sample(
                    timestamp=time.time(),
                    speed_kmh=speed,
                    distance_km=parsed.get("distance_m", 0) / 1000.0,
                    incline_percent=parsed.get("incline_percent", 0)
                )

                self.buffer.add_sample(sample)

                print(f"Samples count = {len(self.buffer.get_samples())}")

            # =========================
            # WORKOUT FINISHED
            # =========================

            if event == "finished":

                print("\n=== WORKOUT FINISHED ===\n")

                print(f"Samples recorded : {len(self.buffer.get_samples())}")

                self.buffer.trim_after_timestamp(
                    self.detector.session_end_time
                )

                print(f"Samples recorded : {len(self.buffer.get_samples())}")

                # Debug first samples
                for s in self.buffer.get_samples()[:5]:
                    print(s)

                print("TODO: save Garmin FIT file")

        await self.client.start_notify(
            TREADMILL_DATA_UUID,
            notification_handler
        )

        print("Notify started successfully")

        print("Listening treadmill notifications...\n")

    async def run(self):

        while True:

            try:

                if not self.connected:

                    await self.connect()

                    await self.start_notifications()

                await asyncio.sleep(1)

            except Exception as e:

                print("BLE error :", e)

                self.connected = False

                await asyncio.sleep(5)

    async def disconnect(self):

        if self.client and self.client.is_connected:

            await self.client.disconnect()

        print("Disconnected")