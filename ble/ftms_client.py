import asyncio
import time
import os

from bleak import BleakClient

from ble.ftms_parser import parse_treadmill_data
from session.workout_detector import WorkoutDetector
from storage.session_buffer import SessionBuffer
from storage.csv_writer import save_session
from storage.fit_writer import save_fit
from model.sample import Sample


TREADMILL_DATA_UUID = "00002acd-0000-1000-8000-00805f9b34fb"

# Where to store output files
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


class FTMSClient:

    def __init__(self, address, garmin_client=None):
        """
        Args:
            address:        BLE address of the treadmill
            garmin_client:  optional GarminClient instance for HR merge + upload.
                            If None, only a CSV + raw FIT (no HR) will be saved.
        """
        self.address        = address
        self.client         = None
        self.connected      = False
        self.detector       = WorkoutDetector()
        self.buffer         = SessionBuffer()
        self.garmin_client  = garmin_client

        os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ─────────────────────────────────────────
    # BLE CONNECTION
    # ─────────────────────────────────────────

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

    # ─────────────────────────────────────────
    # NOTIFICATIONS
    # ─────────────────────────────────────────

    async def start_notifications(self):
        print("Starting notify...")

        def notification_handler(sender, data):
            parsed = parse_treadmill_data(data)
            speed  = parsed.get("speed_kmh", 0)

            event = self.detector.update(speed)

            # ── Record sample while workout is active ──
            if self.detector.is_running:
                sample = Sample(
                    timestamp       = time.time(),
                    speed_kmh       = speed,
                    distance_km     = parsed.get("distance_m", 0) / 1000.0,
                    incline_percent = parsed.get("incline_percent", 0),
                )
                self.buffer.add_sample(sample)
                print(
                    f"  >> {speed:.1f} km/h | "
                    f"{sample.distance_km:.2f} km | "
                    f"samples: {len(self.buffer.get_samples())}",
                    end="\r"
                )

            # ── Workout finished → save ──
            if event == "finished":
                self.buffer.trim_after_timestamp(self.detector.session_end_time)
                samples = self.buffer.get_samples()
                print(f"\n\n=== WORKOUT FINISHED - {len(samples)} samples ===\n")

                # Use get_running_loop() — works on Windows Python 3.10+
                loop = asyncio.get_running_loop()
                loop.create_task(self._save_and_upload(list(samples)))
                self.buffer.clear()

        await self.client.start_notify(TREADMILL_DATA_UUID, notification_handler)
        print("Listening for treadmill notifications...\n")

    # ─────────────────────────────────────────
    # SAVE → MERGE → UPLOAD PIPELINE
    # ─────────────────────────────────────────

    async def _save_and_upload(self, samples: list):
        """
        Full pipeline after a workout ends:
          1. Save CSV (always)
          2. Fetch Garmin HR (if garmin_client is set)
          3. Merge HR into samples
          4. Save merged FIT file
          5. Upload FIT to Garmin Connect
        """
        timestamp_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(samples[0].timestamp))

        # ── 1. Save CSV ──────────────────────────────────────────────────────
        csv_path = os.path.join(OUTPUT_DIR, f"treadmill_{timestamp_str}.csv")
        save_session(samples, csv_path)

        # ── 2. Fetch Garmin HR ───────────────────────────────────────────────
        hr_data = {}
        if self.garmin_client:
            try:
                print("[pipeline] Fetching last Garmin activity HR...")
                hr_data = await asyncio.to_thread(
                    self.garmin_client.get_last_activity_hr
                )
            except Exception as e:
                print(f"[pipeline] Could not fetch Garmin HR: {e}")
                print("[pipeline] Saving FIT without heart rate data")
        else:
            print("[pipeline] No Garmin client configured — skipping HR fetch")

        # ── 3. Merge ─────────────────────────────────────────────────────────
        merged_hr = {}
        if hr_data:
            from garmin.merger import align_and_merge, print_merge_summary
            merged_hr = align_and_merge(samples, hr_data)
            print_merge_summary(samples, merged_hr)

        # ── 4. Save FIT ──────────────────────────────────────────────────────
        fit_path = os.path.join(OUTPUT_DIR, f"treadmill_{timestamp_str}.fit")
        try:
            save_fit(samples, fit_path, hr_data=merged_hr)
        except Exception as e:
            print(f"[pipeline] FIT write failed: {e}")
            return

        # ── 5. Upload to Garmin Connect ──────────────────────────────────────
        if self.garmin_client:
            try:
                print("[pipeline] Uploading FIT to Garmin Connect...")
                await asyncio.to_thread(self.garmin_client.upload_fit, fit_path)
                print("[pipeline] Upload complete ✓")
            except Exception as e:
                print(f"[pipeline] Upload failed: {e}")
                print(f"[pipeline] FIT file saved locally at: {fit_path}")
        else:
            print(f"[pipeline] FIT saved locally (no upload): {fit_path}")

    # ─────────────────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────────────────

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