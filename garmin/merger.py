"""
Merger: aligns treadmill samples with Garmin HR data.

The treadmill BLE session starts at a different unix timestamp
than the Garmin activity (watch started first / later).

Strategy:
  - Both datasets are time-series starting near the same moment.
  - We align them by offsetting the Garmin HR stream to match
    the treadmill session start.
  - Then for each treadmill sample, we interpolate the nearest HR value.
"""

from typing import Optional




def align_and_merge(
    treadmill_samples: list,
    garmin_hr: dict,
    offset_seconds: float = None,
) -> dict:
    """
    Align Garmin HR data to treadmill session timestamps.

    Args:
        treadmill_samples: list of Sample (with .timestamp in unix seconds)
        garmin_hr:         dict {unix_ts: bpm} from GarminClient
        offset_seconds:    manual offset to apply to garmin HR timestamps.
                           If None, auto-detected by aligning stream starts.

    Returns:
        dict {unix_ts: bpm} aligned to treadmill timestamps
    """
    if not garmin_hr:
        print("[merger] No Garmin HR data — FIT will have no heart rate")
        return {}

    if not treadmill_samples:
        raise ValueError("No treadmill samples to merge with")

    treadmill_start = treadmill_samples[0].timestamp
    treadmill_end   = treadmill_samples[-1].timestamp

    garmin_start    = min(garmin_hr.keys())
    garmin_end      = max(garmin_hr.keys())

    print(f"[merger] Treadmill session : {_fmt(treadmill_start)} → {_fmt(treadmill_end)}")
    print(f"[merger] Garmin HR stream  : {_fmt(garmin_start)} → {_fmt(garmin_end)}")

    # ── Compute offset ───────────────────────────────────────────────────────
    if offset_seconds is None:
        # Auto: assume both activities started at roughly the same time.
        # Shift Garmin HR so its start aligns with treadmill start.
        offset_seconds = treadmill_start - garmin_start
        print(f"[merger] Auto offset: {offset_seconds:+.1f}s "
              f"({'garmin is ahead' if offset_seconds < 0 else 'treadmill is ahead'})")
    else:
        print(f"[merger] Manual offset: {offset_seconds:+.1f}s")

    # ── Shift Garmin HR timestamps ───────────────────────────────────────────
    shifted_hr = {
        ts + offset_seconds: bpm
        for ts, bpm in garmin_hr.items()
    }

    # ── Build lookup: for each treadmill sample, find nearest HR ─────────────
    sorted_hr_ts = sorted(shifted_hr.keys())

    aligned = {}
    missing = 0

    for sample in treadmill_samples:
        ts  = sample.timestamp
        bpm = _interpolate_hr(ts, sorted_hr_ts, shifted_hr)
        if bpm is not None:
            aligned[ts] = bpm
        else:
            missing += 1

    coverage = (len(aligned) / len(treadmill_samples)) * 100 if treadmill_samples else 0
    print(f"[merger] HR coverage: {len(aligned)}/{len(treadmill_samples)} samples ({coverage:.0f}%)")
    if missing:
        print(f"[merger] {missing} samples had no HR within ±10s window")

    return aligned


def _interpolate_hr(
    target_ts: float,
    sorted_hr_ts: list,
    hr_map: dict,
    max_gap_s: float = 10.0,
) -> Optional[int]:
    """
    Linear interpolation of HR at target_ts from the sorted HR stream.
    Returns None if the nearest point is further than max_gap_s.
    """
    if not sorted_hr_ts:
        return None

    # Binary search for insertion point
    lo, hi = 0, len(sorted_hr_ts) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_hr_ts[mid] < target_ts:
            lo = mid + 1
        else:
            hi = mid

    # lo is now the index of the first ts >= target_ts
    candidates = []
    if lo > 0:
        candidates.append(lo - 1)
    if lo < len(sorted_hr_ts):
        candidates.append(lo)

    best = min(candidates, key=lambda i: abs(sorted_hr_ts[i] - target_ts))
    best_ts = sorted_hr_ts[best]

    if abs(best_ts - target_ts) > max_gap_s:
        return None

    # Linear interpolation between neighbours if both exist
    if lo > 0 and lo < len(sorted_hr_ts):
        t0, t1 = sorted_hr_ts[lo - 1], sorted_hr_ts[lo]
        v0, v1 = hr_map[t0], hr_map[t1]
        if t1 != t0:
            ratio = (target_ts - t0) / (t1 - t0)
            return int(round(v0 + ratio * (v1 - v0)))

    return hr_map[best_ts]


def print_merge_summary(samples: list, hr_data: dict):
    """Print a human-readable summary of the merged session."""
    if not samples:
        return

    elapsed = samples[-1].timestamp - samples[0].timestamp
    avg_speed = sum(s.speed_kmh for s in samples) / len(samples)
    max_speed = max(s.speed_kmh for s in samples)
    total_dist = samples[-1].distance_km

    hr_values = list(hr_data.values())
    avg_hr = int(sum(hr_values) / len(hr_values)) if hr_values else None
    max_hr = max(hr_values) if hr_values else None

    print("\n" + "=" * 40)
    print("  MERGED SESSION SUMMARY")
    print("=" * 40)
    print(f"  Duration    : {int(elapsed // 60)}m {int(elapsed % 60)}s")
    print(f"  Distance    : {total_dist:.2f} km")
    print(f"  Avg speed   : {avg_speed:.1f} km/h")
    print(f"  Max speed   : {max_speed:.1f} km/h")
    if avg_hr:
        print(f"  Avg HR      : {avg_hr} bpm")
        print(f"  Max HR      : {max_hr} bpm")
    else:
        print(f"  Heart rate  : not available")
    print("=" * 40 + "\n")


def _fmt(unix_ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(unix_ts).strftime("%H:%M:%S")
