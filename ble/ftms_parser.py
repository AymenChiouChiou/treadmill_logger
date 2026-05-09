def parse_treadmill_data(data: bytes):

    result = {}

    # =========================
    # FLAGS
    # =========================

    flags = int.from_bytes(data[0:2], byteorder="little")

    result["flags"] = flags

    offset = 2

    # =========================
    # INSTANTANEOUS SPEED
    # always present
    # uint16 / 100
    # =========================

    speed_raw = int.from_bytes(
        data[offset:offset + 2],
        byteorder="little"
    )

    result["speed_kmh"] = speed_raw / 100.0

    offset += 2

    # =========================
    # TOTAL DISTANCE
    # flag bit 2
    # uint24 meters
    # =========================

    if flags & (1 << 2):

        distance_raw = int.from_bytes(
            data[offset:offset + 3],
            byteorder="little"
        )

        result["distance_m"] = distance_raw

        offset += 3

    # =========================
    # INCLINE
    # flag bit 3
    # sint16 / 10
    # =========================

    if flags & (1 << 3):

        incline_raw = int.from_bytes(
            data[offset:offset + 2],
            byteorder="little",
            signed=True
        )

        result["incline_percent"] = incline_raw / 10.0

        offset += 2

    return result