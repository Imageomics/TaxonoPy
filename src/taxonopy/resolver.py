import requests

def resolve_species(identifiers):
    endpoint = 'http://resolver.globalnames.org/name_resolvers.json'
    params = {
        'names': '|'.join(identifiers),
        'with_canonical_ranks': 'true'
    }
    response = requests.get(endpoint, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()  
