class SessionBuffer:
    def __init__(self):
        self.samples = []

    def add_sample(self, sample):
        self.samples.append(sample)

    def get_samples(self):
        return self.samples

    def clear(self):
        self.samples.clear()