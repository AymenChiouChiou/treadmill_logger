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

        def notification_handler(sender, data):

            parsed = parse_treadmill_data(data)

            print(parsed)

            speed = parsed.get("speed_kmh", 0)

            event = self.detector.update(speed)

            # =========================
            # STORE SAMPLE
            # =========================

            if self.detector.is_running:
                sample = Sample(
                    timestamp=time.time(),
                    speed_kmh=speed,
                    distance_km=parsed.get("distance_m", 0) / 1000.0,
                    incline_percent=parsed.get("incline_percent", 0)
                )

                self.buffer.add_sample(sample)

            # =========================
            # WORKOUT FINISHED
            # =========================

            if event == "finished":

                print(f"Samples recorded : {len(self.buffer.get_samples())}")

                # temporary debug
                for s in self.buffer.get_samples()[:5]:
                    print(s)

                print("TODO: save Garmin FIT file")

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