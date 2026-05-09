"""
FIT file writer for treadmill session data.
Uses only Python stdlib (struct) — no external FIT library needed.
"""

import struct
from model.sample import Sample


# -----------------------------------------
# FIT PROTOCOL CONSTANTS
# -----------------------------------------

FIT_HEADER_SIZE     = 14
FIT_PROTOCOL_VER    = 0x10
FIT_PROFILE_VER     = 2132
GARMIN_MANUFACTURER = 1
GARMIN_PRODUCT      = 1

MESG_FILE_ID        = 0
MESG_ACTIVITY       = 34
MESG_SESSION        = 18
MESG_LAP            = 19
MESG_RECORD         = 20
MESG_EVENT          = 21

BASE_ENUM           = 0x00
BASE_UINT8          = 0x02
BASE_UINT16         = 0x84
BASE_UINT32         = 0x86
BASE_UINT32Z        = 0x8C

FIT_EPOCH = 631065600

LOCAL_FILE_ID   = 0
LOCAL_EVENT     = 1
LOCAL_RECORD    = 2
LOCAL_LAP       = 3
LOCAL_SESSION   = 4
LOCAL_ACTIVITY  = 5


def unix_to_fit(unix_ts: float) -> int:
    return max(0, int(unix_ts) - FIT_EPOCH)


def crc16(data: bytes) -> int:
    CRC_TABLE = [
        0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
    ]
    crc = 0
    for byte in data:
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ CRC_TABLE[byte & 0xF]
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def _definition_message(local_mesg_num: int, global_mesg_num: int, fields: list) -> bytes:
    header = 0x40 | (local_mesg_num & 0x0F)
    msg = struct.pack("BBBHB", header, 0, 0, global_mesg_num, len(fields))
    for field_def, size, base_type in fields:
        msg += struct.pack("BBB", field_def, size, base_type)
    return msg


def _build_file_id(time_created: int) -> bytes:
    definition = _definition_message(LOCAL_FILE_ID, MESG_FILE_ID, [
        (0, 1, BASE_ENUM),
        (1, 2, BASE_UINT16),
        (2, 2, BASE_UINT16),
        (4, 4, BASE_UINT32Z),
    ])
    # 5 values: local_id, type, manufacturer, product, serial
    data = struct.pack("<BBHHI",
        LOCAL_FILE_ID,
        4,                    # type = activity
        GARMIN_MANUFACTURER,
        GARMIN_PRODUCT,
        time_created,
    )
    return definition + data


def _build_event(local_num: int, fit_ts: int, event: int, event_type: int, data: int = 0) -> bytes:
    definition = _definition_message(LOCAL_EVENT, MESG_EVENT, [
        (253, 4, BASE_UINT32),
        (0,   1, BASE_ENUM),
        (1,   1, BASE_ENUM),
        (3,   4, BASE_UINT32),
    ])
    # 5 values: local_id, timestamp, event, event_type, data
    data_msg = struct.pack("<BIBBI",
        LOCAL_EVENT,
        fit_ts,
        event,
        event_type,
        data,
    )
    return definition + data_msg


def _def_record() -> bytes:
    return _definition_message(LOCAL_RECORD, MESG_RECORD, [
        (253, 4, BASE_UINT32),  # timestamp
        (6,   2, BASE_UINT16),  # speed (mm/s)
        (5,   4, BASE_UINT32),  # distance (cm)
        (3,   1, BASE_UINT8),   # heart_rate
        (7,   1, BASE_UINT8),   # cadence
        (2,   2, BASE_UINT16),  # altitude
    ])


def _data_record(fit_ts: int, speed_kmh: float, distance_km: float,
                 heart_rate: int, incline_percent: float) -> bytes:
    speed_ms1000 = int(speed_kmh / 3.6 * 1000)
    distance_cm  = int(distance_km * 1000 * 100)
    hr           = heart_rate if heart_rate > 0 else 0xFF
    altitude_raw = 500   # 0m elevation encoded as 0*5+500

    # 7 values: local_id, timestamp, speed, distance, hr, cadence, altitude
    return struct.pack("<BIHIBBH",
        LOCAL_RECORD,
        fit_ts,
        speed_ms1000,
        distance_cm,
        hr,
        0xFF,        # cadence = invalid
        altitude_raw,
    )


def _def_lap() -> bytes:
    return _definition_message(LOCAL_LAP, MESG_LAP, [
        (253, 4, BASE_UINT32),  # timestamp
        (2,   4, BASE_UINT32),  # start_time
        (7,   4, BASE_UINT32),  # total_elapsed_time (ms)
        (9,   4, BASE_UINT32),  # total_distance (cm)
        (11,  2, BASE_UINT16),  # avg_speed (mm/s)
        (15,  1, BASE_UINT8),   # avg_heart_rate
        (25,  1, BASE_ENUM),    # lap_trigger
    ])


def _data_lap(fit_ts: int, start_ts: int, elapsed_s: float,
              total_dist_km: float, avg_speed_kmh: float, avg_hr: int) -> bytes:
    # 8 values: local_id, timestamp, start_time, elapsed, distance, speed, hr, trigger
    return struct.pack("<BIIIIHBB",
        LOCAL_LAP,
        fit_ts,
        start_ts,
        int(elapsed_s * 1000),
        int(total_dist_km * 1000 * 100),
        int(avg_speed_kmh / 3.6 * 1000),
        avg_hr if avg_hr > 0 else 0xFF,
        0,           # lap_trigger = manual
    )


def _def_session() -> bytes:
    return _definition_message(LOCAL_SESSION, MESG_SESSION, [
        (253, 4, BASE_UINT32),  # timestamp
        (2,   4, BASE_UINT32),  # start_time
        (7,   4, BASE_UINT32),  # total_elapsed_time (ms)
        (9,   4, BASE_UINT32),  # total_distance (cm)
        (14,  2, BASE_UINT16),  # avg_speed (mm/s)
        (16,  2, BASE_UINT16),  # max_speed (mm/s)
        (18,  1, BASE_UINT8),   # avg_heart_rate
        (19,  1, BASE_UINT8),   # max_heart_rate
        (0,   1, BASE_ENUM),    # event
        (1,   1, BASE_ENUM),    # event_type
        (5,   1, BASE_ENUM),    # sport
        (6,   1, BASE_ENUM),    # sub_sport
    ])


def _data_session(fit_ts: int, start_ts: int, elapsed_s: float,
                  total_dist_km: float, avg_speed_kmh: float, max_speed_kmh: float,
                  avg_hr: int, max_hr: int) -> bytes:
    # 13 values: local_id, ts, start, elapsed, dist, avg_spd, max_spd,
    #            avg_hr, max_hr, event, event_type, sport, sub_sport
    return struct.pack("<BIIIIHH BBBBBB".replace(" ", ""),
        LOCAL_SESSION,
        fit_ts,
        start_ts,
        int(elapsed_s * 1000),
        int(total_dist_km * 1000 * 100),
        int(avg_speed_kmh / 3.6 * 1000),
        int(max_speed_kmh / 3.6 * 1000),
        avg_hr if avg_hr > 0 else 0xFF,
        max_hr if max_hr > 0 else 0xFF,
        9,           # event = session
        1,           # event_type = stop
        1,           # sport = running
        17,          # sub_sport = indoor_running/treadmill
    )


def _def_activity() -> bytes:
    return _definition_message(LOCAL_ACTIVITY, MESG_ACTIVITY, [
        (253, 4, BASE_UINT32),  # timestamp
        (1,   4, BASE_UINT32),  # total_timer_time (ms)
        (2,   2, BASE_UINT16),  # num_sessions
        (3,   1, BASE_ENUM),    # type
        (4,   1, BASE_ENUM),    # event
        (5,   1, BASE_ENUM),    # event_type
    ])


def _data_activity(fit_ts: int, elapsed_s: float) -> bytes:
    # 7 values: local_id, timestamp, elapsed, num_sessions, type, event, event_type
    return struct.pack("<BIIHBBB",
        LOCAL_ACTIVITY,
        fit_ts,
        int(elapsed_s * 1000),
        1,           # num_sessions
        0,           # type = manual
        26,          # event = activity
        1,           # event_type = stop
    )


# -----------------------------------------
# PUBLIC API
# -----------------------------------------

def save_fit(samples: list, filepath: str, hr_data: dict = None):
    if not samples:
        raise ValueError("No samples to save")

    hr_data    = hr_data or {}
    start_unix = samples[0].timestamp
    end_unix   = samples[-1].timestamp
    elapsed_s  = end_unix - start_unix
    start_fit  = unix_to_fit(start_unix)
    end_fit    = unix_to_fit(end_unix)

    speeds     = [s.speed_kmh for s in samples]
    avg_speed  = sum(speeds) / len(speeds)
    max_speed  = max(speeds)
    total_dist = samples[-1].distance_km

    hr_values  = [v for v in hr_data.values() if v and v > 0]
    avg_hr     = int(sum(hr_values) / len(hr_values)) if hr_values else 0
    max_hr     = max(hr_values) if hr_values else 0

    def _nearest_hr(unix_ts: float) -> int:
        if not hr_data:
            return 0
        best_ts = min(hr_data.keys(), key=lambda t: abs(t - unix_ts))
        if abs(best_ts - unix_ts) <= 5:
            return hr_data[best_ts]
        return 0

    body  = b""
    body += _build_file_id(start_fit)
    body += _build_event(LOCAL_EVENT, start_fit, event=0, event_type=0)
    body += _def_record()

    for sample in samples:
        fit_ts = unix_to_fit(sample.timestamp)
        hr     = _nearest_hr(sample.timestamp)
        body  += _data_record(
            fit_ts          = fit_ts,
            speed_kmh       = sample.speed_kmh,
            distance_km     = sample.distance_km,
            heart_rate      = hr,
            incline_percent = sample.incline_percent,
        )

    body += _def_lap()
    body += _data_lap(
        fit_ts        = end_fit,
        start_ts      = start_fit,
        elapsed_s     = elapsed_s,
        total_dist_km = total_dist,
        avg_speed_kmh = avg_speed,
        avg_hr        = avg_hr,
    )

    body += _def_session()
    body += _data_session(
        fit_ts        = end_fit,
        start_ts      = start_fit,
        elapsed_s     = elapsed_s,
        total_dist_km = total_dist,
        avg_speed_kmh = avg_speed,
        max_speed_kmh = max_speed,
        avg_hr        = avg_hr,
        max_hr        = max_hr,
    )

    body += _def_activity()
    body += _data_activity(fit_ts=end_fit, elapsed_s=elapsed_s)

    data_size  = len(body)
    header     = struct.pack("<BBHIHH",
        FIT_HEADER_SIZE,
        FIT_PROTOCOL_VER,
        FIT_PROFILE_VER,
        data_size,
        0x5449462E,  # ".FIT" magic
        0x0000,
    )
    header_crc = crc16(header[:12])
    header     = header[:12] + struct.pack("<H", header_crc)

    body_crc   = crc16(body)
    body      += struct.pack("<H", body_crc)

    with open(filepath, "wb") as f:
        f.write(header + body)

    print(f"[fit_writer] Saved {len(samples)} records -> {filepath} ({FIT_HEADER_SIZE + len(body)} bytes)")
    return filepath