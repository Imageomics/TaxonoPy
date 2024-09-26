import subprocess
import json
from taxonopy.utils import extract_required_ranks

class ContainerHandler:
    # GBIF is default prioritized data source with ID 11
    def __init__(self, image="gnames/gnverifier:v1.2.0", prioritized_data_source_id="11"):
        self.image = image
        self.prioritized_data_source_id = prioritized_data_source_id
        self.required_ranks = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']

    def run_container(self, input_file, output_file):
        """
        Run the GNVerifier container using Docker.
        """
        try:
            with open(input_file, "rb") as f:
                result = subprocess.run(
                    [
                        "docker", "run", "--rm", "-i",
                        self.image,
                        "--format", "compact", 
                        "--sources", self.prioritized_data_source_id
                    ],
                    stdin=f,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

            # Save results to output file
            with open(output_file, "wb") as out_file:
                out_file.write(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error running Docker container: {e.stderr.decode('utf-8')}")
            raise

    def is_docker_available(self):
        """Check if Docker is available on the system."""
        try:
            subprocess.run(["docker", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError:
            return False
