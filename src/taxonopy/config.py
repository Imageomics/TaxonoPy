class Config:
    def __init__(self):
        self.GNR_ENDPOINT = "http://resolver.globalnames.org/name_resolvers.json"

    def get_endpoint(self):
        return self.GNR_ENDPOINT