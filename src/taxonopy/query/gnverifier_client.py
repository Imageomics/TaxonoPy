"""GNVerifier client for TaxonoPy.

This module provides a client for interacting with the GNVerifier service through a Docker container or a local installation.
It handles execution, result parsing, and error handling.
"""
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union, Any

from taxonopy.types.gnverifier import VerificationOutput, Name
from taxonopy.config import config

@dataclass
class GNVerifierConfig:
    """Configuration for the GNVerifier client."""
    
    # Docker image to use for container-based execution
    gnverifier_image: str = field(default_factory=lambda: config.gnverifier_image)

    # Data sources to query (comma-separated IDs)
    data_source_id: str = field(default_factory=lambda: config.data_source_id)
    
    # Whether to return all matches instead of just the best one
    all_matches: bool = field(default_factory=lambda: config.all_matches)
    
    # Whether to capitalize the first letter of each name
    capitalize: bool = field(default_factory=lambda: config.capitalize)
    
    # Number of parallel jobs to run
    jobs: int = field(default_factory=lambda: config.jobs)
    
    # Output format (compact, pretty, csv, tsv)
    format: str = "compact"
    
    # Whether to enable group species matching
    species_group: bool = field(default_factory=lambda: config.species_group)
    
    # Whether to enable fuzzy matching for uninomial names
    fuzzy_uninomial: bool = field(default_factory=lambda: config.fuzzy_uninomial)
    
    # Whether to relax fuzzy matching criteria
    fuzzy_relaxed: bool = field(default_factory=lambda: config.fuzzy_relaxed)

class GNVerifierClient:
    """Client for interacting with the Global Names Verifier service."""

    def __init__(self, config_obj: Optional[GNVerifierConfig] = None):
        """Initialize the GNVerifier client."""
        self.logger = logging.getLogger(__name__)
        if config_obj:
            self.config = config_obj
        else:
            self.config = GNVerifierConfig() # Use defaults from class definition

        # Check and update flags based on global config if defaults were used
        # Ensures CLI args passed to global config are respected
        # if no specific config_obj was provided to the client.
        if not config_obj:
             self.config.gnverifier_image = config.gnverifier_image
             self.config.data_source_id = config.data_source_id # Assumes global config holds the preferred source list/string
             self.config.all_matches = config.all_matches
             self.config.capitalize = config.capitalize
             self.config.jobs = config.jobs # Use global job count if specified
             self.config.species_group = config.species_group
             self.config.fuzzy_uninomial = config.fuzzy_uninomial
             self.config.fuzzy_relaxed = config.fuzzy_relaxed
             # Note: format is fixed to 'compact' for JSON parsing

        self.use_docker, self.gnverifier_available = self._determine_execution_method()
    
    def _determine_execution_method(self) -> Tuple[bool, bool]:
        """Determine whether to use Docker or local installation.
        
        Returns:
            Tuple containing:
            - use_docker (bool): Whether to use Docker
            - gnverifier_available (bool): Whether GNVerifier is available
        """
        if self._is_docker_available():
            # Check if the image is available
            if self._is_docker_image_available(self.config.gnverifier_image):
                self.logger.info(f"Using GNVerifier via Docker with image {self.config.gnverifier_image}")
                return True, True
            
            # Try to pull the image
            try:
                self._pull_docker_image(self.config.gnverifier_image)
                self.logger.info(f"Pulled GNVerifier Docker image {self.config.gnverifier_image}")
                return True, True
            except RuntimeError as e:
                self.logger.error(f"Failed to pull Docker image: {e}")
                # Fall back to local installation
        
        # If Docker is not available or failed, check for local installation
        if self._is_gnverifier_installed():
            self.logger.info("Using local GNVerifier installation")
            return False, True
        
        # Neither Docker nor local installation is available
        self.logger.warning("GNVerifier not found via Docker or local installation")
        self.logger.warning("Please install GNVerifier or set up Docker with the GNVerifier image")
        return False, False
    
    def _is_docker_available(self) -> bool:
        """Check if Docker is installed and accessible.
        
        Returns:
            bool: Whether Docker is available
        """
        return shutil.which("docker") is not None
    
    def _is_docker_image_available(self, image: str) -> bool:
        """Check if a Docker image is available locally.
        
        Args:
            image: Docker image name
            
        Returns:
            bool: Whether the image is available
        """
        try:
            result = subprocess.run(
                ["docker", "images", "-q", image],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # timeout=30
            )
            return bool(result.stdout.strip())
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"Error checking Docker image availability: {e}")
            return False
    
    def _pull_docker_image(self, image: str) -> None:
        """Pull a Docker image.
        
        Args:
            image: Docker image name
            
        Raises:
            RuntimeError: If pulling the image fails
        """
        try:
            self.logger.info(f"Pulling Docker image: {image}")
            result = subprocess.run(
                ["docker", "pull", image],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # timeout=300
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            error_msg = f"Failed to pull Docker image '{image}': {str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _is_gnverifier_installed(self) -> bool:
        """Check if GNVerifier is installed locally.
        
        Returns:
            bool: Whether GNVerifier is available
        """
        return shutil.which("gnverifier") is not None
    
    def execute_query(self, names: List[str], source_id_override: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Verify a list of scientific names using GNVerifier.

        Args:
            names: List of scientific names to verify in this batch.
            source_id_override: Optional specific source ID (as string) to use,
                                overriding the client's default config.

        Returns:
            List of verification result dictionaries, one for each input name,
            in the same order. Returns an empty dictionary {} for a name if
            an error occurs during its processing or parsing within the batch.

        Raises:
            RuntimeError: If GNVerifier is not available or a fatal execution error occurs
                          (e.g., non-zero exit code from the gnverifier process).
                          Individual parsing errors are handled internally and result
                          in {} entries in the output list.
        """
        if not self.gnverifier_available:
            error_msg = "GNVerifier is not available via Docker or local installation"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        if not names:
            return [] # Return empty list if no names provided

        # Prepare input for the command-line tool (newline-separated)
        query_input = "\n".join(names)

        # Run verification using the determined method
        try:
            if self.use_docker:
                return self._run_with_docker(query_input, len(names), source_id_override)
            else:
                return self._run_with_local_gnverifier(query_input, len(names), source_id_override)
        except RuntimeError as e:
             self.logger.error(f"Fatal error during GNVerifier execution: {e}")
             raise
        except Exception as e:
            self.logger.error(f"Unexpected error executing GNVerifier query: {e}", exc_info=True)
            return [{} for _ in range(len(names))]
    
    def _run_with_docker(
        self, 
        query_input: str, 
        expected_count: int, 
        source_id_override: Optional[str] = None
    ) -> List[Dict[str, Any]]:        
        """Run GNVerifier using Docker.
        
        Args:
            query_input: Input string with names separated by newlines
            expected_count: Expected number of results
            
        Returns:
            List of verification results
            
        Raises:
            RuntimeError: If execution fails
        """
        cmd = [
            "docker", "run",
            "--rm",
            "-i",
            self.config.gnverifier_image,
            "-j", str(self.config.jobs),
            "--format", self.config.format
        ]
        
        # Add optional flags
        source_to_use = source_id_override if source_id_override is not None else self.config.data_source_id

        if source_to_use: # Check if non-empty/None
            cmd.extend(["--sources", str(source_to_use)])
        
        if self.config.all_matches:
            cmd.append("--all_matches")
        
        if self.config.capitalize:
            cmd.append("--capitalize")
        
        if self.config.species_group:
            cmd.append("--species_group")
        
        if self.config.fuzzy_uninomial:
            cmd.append("--fuzzy_uninomial")
        
        if self.config.fuzzy_relaxed:
            cmd.append("--fuzzy_relaxed")
        
        try:
            self.logger.debug(f"Running Docker command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                input=query_input.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # timeout=600  # 10 minutes
            )
            
            if result.returncode != 0:
                error_output = result.stderr.decode("utf-8").strip()
                error_msg = f"GNVerifier Docker execution failed: {error_output}"
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            output = result.stdout.decode("utf-8")
            return self._parse_gnverifier_output(output, expected_count)
            
        except subprocess.TimeoutExpired:
            self.logger.error("GNVerifier Docker execution timed out")
            return [{} for _ in range(expected_count)]
    
    def _run_with_local_gnverifier(
            self, 
            query_input: str, 
            expected_count: int, 
            source_id_override: Optional[str] = None
        ) -> List[Dict[str, Any]]:        
        """Run GNVerifier using local installation.
        
        Args:
            query_input: Input string with names separated by newlines
            expected_count: Expected number of results
            
        Returns:
            List of verification results
            
        Raises:
            RuntimeError: If execution fails
        """
        cmd = ["gnverifier"]
        
        # Add optional flags
        cmd.extend(["-j", str(self.config.jobs)])
        cmd.extend(["--format", self.config.format])

        source_to_use = source_id_override if source_id_override is not None else self.config.data_source_id
        
        if source_to_use:
            cmd.extend(["--sources", str(source_to_use)])
        
        if self.config.all_matches:
            cmd.append("--all_matches")
        
        if self.config.capitalize:
            cmd.append("--capitalize")
        
        if self.config.species_group:
            cmd.append("--species_group")
        
        if self.config.fuzzy_uninomial:
            cmd.append("--fuzzy_uninomial")
        
        if self.config.fuzzy_relaxed:
            cmd.append("--fuzzy_relaxed")
        
        try:
            self.logger.debug(f"Running local command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                input=query_input.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # timeout=600  # 10 minutes
            )
            
            if result.returncode != 0:
                error_output = result.stderr.decode("utf-8").strip()
                error_msg = f"Local GNVerifier execution failed: {error_output}"
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            output = result.stdout.decode("utf-8")
            return self._parse_gnverifier_output(output, expected_count)
            
        except subprocess.TimeoutExpired:
            self.logger.error("Local GNVerifier execution timed out")
            return [{} for _ in range(expected_count)]
    
    def _parse_gnverifier_output(self, output: str, expected_count: int) -> List[Dict[str, Any]]:
        """Parse GNVerifier output into a list of dictionaries.
        
        Args:
            output: GNVerifier output string
            expected_count: Expected number of results
            
        Returns:
            List of parsed results
        """
        results = []
        lines = output.strip().splitlines()
        
        for i, line in enumerate(lines):
            # Skip log lines (they start with date or other non-JSON content)
            if not line.startswith("{"):
                self.logger.debug(f"Skipping non-JSON line: {line}")
                continue
            
            try:
                result = json.loads(line)
                results.append(result)
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse GNVerifier output line {i+1}: {e}")
                self.logger.debug(f"Problematic line: {line}")
                results.append({})
        
        # Validate the number of results
        if len(results) != expected_count:
            self.logger.warning(f"Expected {expected_count} results but got {len(results)}")
            # Pad with empty dictionaries if needed
            while len(results) < expected_count:
                results.append({})
        
        return results
    
    def validate_response(self, response: Dict[str, Any]) -> bool:
        """Validate a GNVerifier response to ensure it has the expected structure.
        
        Args:
            response: GNVerifier response dictionary
            
        Returns:
            Whether the response is valid
        """
        # Check for minimum required fields
        if not response:
            return False
        
        required_fields = ["name", "matchType"]
        for field in required_fields:
            if field not in response:
                self.logger.warning(f"Response missing required field: {field}")
                return False
        
        return True
