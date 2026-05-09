"""
Garmin Connect client.

Wraps the `garminconnect` library to:
  1. Authenticate (with token caching so you don't re-login every run)
  2. Fetch the last activity's heart rate trackpoints
  3. Upload a merged FIT file back to Garmin Connect

Install:
    pip install garminconnect

Usage:
    client = GarminClient(email="you@example.com", password="secret")
    client.login()
    hr_data = client.get_last_activity_hr()   # {unix_ts: bpm}
    client.upload_fit("merged.fit")
"""

import os
import json
import time
import datetime

try:
    import garminconnect
except ImportError:
    raise ImportError(
        "garminconnect is not installed.\n"
        "Run: pip install garminconnect"
    )


# Path to cache the Garmin auth token between runs
TOKEN_CACHE_PATH = os.path.join(
    os.path.dirname(__file__), ".garmin_token_cache.json"
)


class GarminClient:

    def __init__(self, email: str = None, password: str = None):
        """
        Credentials can be passed directly or via environment variables:
            GARMIN_EMAIL
            GARMIN_PASSWORD
        """
        self.email    = email    or os.environ.get("GARMIN_EMAIL")
        self.password = password or os.environ.get("GARMIN_PASSWORD")
        self.api      = None

        if not self.email or not self.password:
            raise ValueError(
                "Garmin credentials missing.\n"
                "Pass email/password or set GARMIN_EMAIL / GARMIN_PASSWORD env vars."
            )

    # ─────────────────────────────────────────
    # AUTH
    # ─────────────────────────────────────────

    def login(self):
        """
        Authenticate with Garmin Connect.
        Tries to reuse a cached token first to avoid repeated logins.
        """
        self.api = garminconnect.Garmin(self.email, self.password)

        # Try cached token
        if os.path.exists(TOKEN_CACHE_PATH):
            try:
                with open(TOKEN_CACHE_PATH, "r") as f:
                    token = json.load(f)
                self.api.login(token)
                print("[garmin] Logged in with cached token")
                return
            except Exception as e:
                print(f"[garmin] Token cache failed ({e}), re-authenticating...")

        # Fresh login
        self.api.login()
        self._save_token()
        print("[garmin] Logged in successfully")

    def _save_token(self):
        try:
            token = self.api.garth.dumps()
            with open(TOKEN_CACHE_PATH, "w") as f:
                json.dump(token, f)
        except Exception as e:
            print(f"[garmin] Could not cache token: {e}")

    def _ensure_logged_in(self):
        if self.api is None:
            raise RuntimeError("Not logged in. Call client.login() first.")

    # ─────────────────────────────────────────
    # FETCH LAST ACTIVITY
    # ─────────────────────────────────────────

    def get_last_activity(self) -> dict:
        """Return the most recent activity metadata dict."""
        self._ensure_logged_in()
        activities = self.api.get_activities(0, 1)   # offset=0, limit=1
        if not activities:
            raise RuntimeError("No activities found on Garmin Connect.")
        activity = activities[0]
        print(f"[garmin] Last activity: {activity.get('activityName')} "
              f"| {activity.get('startTimeLocal')} "
              f"| id={activity.get('activityId')}")
        return activity

    def get_last_activity_hr(self) -> dict:
        """
        Fetch heart rate trackpoints from the last Garmin activity.

        Returns:
            dict mapping unix_timestamp (float) → heart_rate_bpm (int)
        """
        self._ensure_logged_in()
        activity = self.get_last_activity()
        activity_id = activity["activityId"]
        return self.get_activity_hr(activity_id)

    def get_activity_hr(self, activity_id: int) -> dict:
        """
        Fetch heart rate data for a specific activity.

        Returns:
            dict mapping unix_timestamp (float) → heart_rate_bpm (int)
        """
        self._ensure_logged_in()

        # Garmin Connect returns HR as a list of {startGMT, heartRate} dicts
        details = self.api.get_activity_hr_in_timezones(activity_id)

        hr_data = {}

        # Fallback: use detailed activity data which has heartRateData
        if not details:
            details = self.api.get_activity_details(activity_id)
            hr_samples = (
                details
                .get("connectIQMeasurements", {})
            )

        # Primary path: heartRateData in activity split summaries
        raw = self.api.get_activity(activity_id)
        hr_trackpoints = self._extract_hr_trackpoints(raw, activity_id)

        print(f"[garmin] Fetched {len(hr_trackpoints)} HR trackpoints for activity {activity_id}")
        return hr_trackpoints

    def _extract_hr_trackpoints(self, activity_raw: dict, activity_id: int) -> dict:
        """
        Extract {unix_ts: bpm} from Garmin's activity detail response.
        Tries multiple API endpoints for compatibility.
        """
        hr_data = {}

        # Strategy 1: activity_split_summaries with heartRateData
        try:
            splits = self.api.get_activity_splits(activity_id)
            # splits contain aggregate data, not per-second — skip
        except Exception:
            pass

        # Strategy 2: get_activity_details returns metrics array
        try:
            details = self.api.get_activity_details(activity_id, maxpoly=100)
            metrics = details.get("activityDetailMetrics", [])

            # Find the heart_rate metric stream
            # Each metric entry: {"metrics": [...values...], "metricsType": "HEART_RATE"}
            start_time_str = activity_raw.get("summaryDTO", {}).get("startTimeGMT")
            if not start_time_str:
                start_time_str = activity_raw.get("startTimeGMT", "")

            if start_time_str:
                start_unix = _garmin_time_to_unix(start_time_str)
            else:
                start_unix = time.time() - 3600  # fallback: 1h ago

            for entry in metrics:
                if entry.get("metricsType") == "HEART_RATE":
                    values = entry.get("metrics", [])
                    for i, v in enumerate(values):
                        if v is not None and v > 0:
                            # each sample is 1 second apart
                            hr_data[start_unix + i] = int(v)
                    break

        except Exception as e:
            print(f"[garmin] Strategy 2 failed: {e}")

        # Strategy 3: get_heart_rates (daily HR, not activity-specific — last resort)
        if not hr_data:
            try:
                today = datetime.date.today().isoformat()
                daily = self.api.get_heart_rates(today)
                values = daily.get("heartRateValues", [])
                for entry in values:
                    if entry and len(entry) == 2 and entry[1]:
                        ts_ms, bpm = entry
                        hr_data[ts_ms / 1000.0] = int(bpm)
                print(f"[garmin] Fell back to daily HR: {len(hr_data)} points")
            except Exception as e:
                print(f"[garmin] Strategy 3 failed: {e}")

        return hr_data

    # ─────────────────────────────────────────
    # UPLOAD
    # ─────────────────────────────────────────

    def upload_fit(self, filepath: str) -> dict:
        """
        Upload a FIT file to Garmin Connect.

        Returns the upload response dict (contains activity ID on success).
        """
        self._ensure_logged_in()

        print(f"[garmin] Uploading {filepath}...")
        with open(filepath, "rb") as f:
            result = self.api.upload_activity(f, os.path.basename(filepath))

        activity_id = result.get("detailedImportResult", {}).get("successes", [{}])
        print(f"[garmin] Upload result: {result}")
        return result

    def delete_activity(self, activity_id: int):
        """Delete an activity (useful for cleanup during testing)."""
        self._ensure_logged_in()
        self.api.delete_activity(activity_id)
        print(f"[garmin] Deleted activity {activity_id}")


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _garmin_time_to_unix(time_str: str) -> float:
    """
    Convert Garmin's GMT time string to a Unix timestamp.
    Handles formats like '2024-03-15 08:30:00' or '2024-03-15T08:30:00.0'
    """
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            dt = datetime.datetime.strptime(time_str, fmt)
            return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse Garmin time: {time_str!r}")
