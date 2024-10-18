import subprocess
import json
from taxonopy.utils import extract_required_ranks

class ContainerHandler:
    # GBIF is default prioritized data source with ID 11
    def __init__(self, image="gnames/gnverifier:v1.2.0", prioritized_data_source_id="11"):
        self.image = image
        self.prioritized_data_source_id = prioritized_data_source_id
        self.required_ranks = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']

    def run_container_with_query(self, query_string):
        """Run GNVerifier container with a query string as input."""
        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm", "-i",
                    self.image,
                    "--format", "compact",
                    "--sources", self.prioritized_data_source_id,
                    "--all_matches",
                ],
                input=query_string.encode('utf-8'),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Parse JSONL results returned by gnverifier
            results = []
            for line in result.stdout.decode('utf-8').splitlines():
                results.append(json.loads(line))
            return results

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

    def run_container_with_batch_query(self, scientific_names, print_raw_output=False):
        """
        Run GNVerifier container with a batch of scientific names.
        """
        try:
            # Join all scientific names into one string separated by newlines
            query_input = "\n".join(scientific_names)

            # Run the Docker container with the batch of names piped at once
            result = subprocess.run(
                [
                    "docker", "run", "--rm", "-i",
                    self.image,
                    "--format", "compact",
                    "--sources", "11,179",  # Including both GBIF and OTOL
                    "--all_matches"
                ],
                input=query_input.encode('utf-8'),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Combine stderr and stdout
            combined_output = result.stderr.decode('utf-8') + result.stdout.decode('utf-8')

            # Print raw output if requested
            if print_raw_output:
                print("Raw output from gnverifier:")
                print(combined_output)

            # Parse the JSONL results returned by GNVerifier
            results = []
            for line in result.stdout.decode('utf-8').splitlines():
                results.append(json.loads(line))

            return results

        except subprocess.CalledProcessError as e:
            print(f"Error running Docker container: {e.stderr.decode('utf-8')}")
            raise
