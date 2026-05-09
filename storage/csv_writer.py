import csv


def save_session(samples, filepath):

    with open(filepath, "w", newline="") as f:

        writer = csv.writer(f)

        writer.writerow([
            "timestamp",
            "speed_kmh",
            "distance_km",
            "incline_percent"
        ])

        for s in samples:
            writer.writerow([
                s.timestamp,
                s.speed_kmh,
                s.distance_km,
                s.incline_percent
            ])

    print(f"Session saved to {filepath}")