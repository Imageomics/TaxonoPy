import requests
from taxonopy.config import Config

class APIService:
    def __init__(self):
        self.config = Config()

    def query_gnr(self, names):
        params = {
            "names": "|".join(names),
            "with_context": "false",
            "with_canonical_ranks": "true"
        }
        endpoint = self.config.get_endpoint()  # Call get_endpoint on the Config class directly
        response = requests.get(endpoint, params=params)
        response.raise_for_status()

        return response.json()
    