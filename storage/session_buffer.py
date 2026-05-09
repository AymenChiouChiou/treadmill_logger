class SessionBuffer:
    def __init__(self):
        self.samples = []

    def add_sample(self, sample):
        self.samples.append(sample)

    def get_samples(self):
        return self.samples

    def clear(self):
        self.samples.clear()

    def trim_after_timestamp(self, timestamp):
        while self.samples:
            last_sample = self.samples[-1]
            if last_sample.speed_kmh == 0:
                self.samples.pop()
            else:
                break
