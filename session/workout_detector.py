import time


class WorkoutDetector:

    def __init__(self):

        self.is_running = False

        self.zero_speed_start = None

        self.session_start_time = None

        self.session_end_time = None

    def update(self, speed_kmh):

        current_time = time.time()

        # =========================
        # START DETECTION
        # =========================

        if not self.is_running:

            if speed_kmh > 1.2:

                self.is_running = True

                self.session_start_time = current_time

                self.zero_speed_start = None

                print("\n=== WORKOUT STARTED ===\n")

                return "started"

        # =========================
        # STOP DETECTION
        # =========================

        else:

            # treadmill stopped
            if speed_kmh == 0:

                # first zero detected
                if self.zero_speed_start is None:

                    self.zero_speed_start = current_time

                    print("Zero speed detected...")

                # zero maintained for 60 sec
                else:

                    elapsed = current_time - self.zero_speed_start

                    if elapsed >= 60:

                        self.is_running = False

                        # IMPORTANT:
                        # end time = first zero detection
                        self.session_end_time = self.zero_speed_start

                        print("\n=== WORKOUT FINISHED ===\n")

                        self.zero_speed_start = None

                        return "finished"

            # treadmill running again
            else:

                self.zero_speed_start = None

        return None