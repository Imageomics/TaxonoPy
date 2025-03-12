"""GNVerifier client for TaxonoPy.

This module provides a client for interacting with the GNVerifier service through a Docker container or a local installation.
It handles execution, result parsing, and error handling.
"""

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union, Any

from taxonopy.types.data_classes import QueryGroupRef
from taxonopy.types.gnverifier import VerificationOutput, Name


@dataclass
class GNVerifierConfig:
    """Configuration for the GNVerifier client."""
    
    # Docker image to use for container-based execution
    gnverifier_image: str = "gnames/gnverifier:v1.2.3"
    
    # Data sources to query (comma-separated IDs)
    data_sources: str = "11"  # Default to GBIF (11)
    
    # Whether to return all matches instead of just the best one
    all_matches: bool = True
    
    # Whether to capitalize the first letter of each name
    capitalize: bool = True
    
    # Number of parallel jobs to run (1 ensures consistent ordering)
    jobs: int = 1
    
    # Output format (compact, pretty, csv, tsv)
    format: str = "compact"
    
    # Whether to enable group species matching
    species_group: bool = False
    
    # Whether to enable fuzzy matching for uninomial names
    fuzzy_uninomial: bool = False
    
    # Whether to relax fuzzy matching criteria
    fuzzy_relaxed: bool = False


class GNVerifierClient:
    """Client for interacting with the Global Names Verifier service."""
    
    def __init__(self, 
                 gnverifier_image: str = "gnames/gnverifier:v1.2.3",
                 data_sources: str = "11",
                 all_matches: bool = True,
                 capitalize: bool = True,
                 config: Optional[GNVerifierConfig] = None):
        """Initialize the GNVerifier client.
        
        Args:
            gnverifier_image: Docker image to use
            data_sources: Data source IDs (comma-separated)
            all_matches: Whether to return all matches
            capitalize: Whether to capitalize name strings
            config: Optional configuration object that overrides other parameters
        """
        # Set up logging for this module
        self.logger = logging.getLogger(__name__)
        # Apply config if provided, otherwise use parameters
        if config:
            self.config = config
        else:
            self.config = GNVerifierConfig(
                gnverifier_image=gnverifier_image,
                data_sources=data_sources,
                all_matches=all_matches,
                capitalize=capitalize
            )
        
        # Determine execution method
        self.use_docker, self.gnverifier_available = self._determine_execution_method()
    
    def _determine_execution_method(self) -> Tuple[bool, bool]:
        """Determine whether to use Docker or local installation.
        
        Returns:
            Tuple containing:
            - use_docker (bool): Whether to use Docker
            - gnverifier_available (bool): Whether GNVerifier is available
        """
        # First, check Docker availability
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
                # timeout=300  # 5 minutes
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
    
    def execute_query(self, names: List[str]) -> List[Dict[str, Any]]:
        """Verify scientific names using GNVerifier.
        
        Args:
            names: List of scientific names to verify
            
        Returns:
            List of verification results as dictionaries
            
        Raises:
            RuntimeError: If GNVerifier is not available or execution fails
        """
        if not self.gnverifier_available:
            error_msg = "GNVerifier is not available via Docker or local installation"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # Prepare input
        query_input = "\n".join(names)
        
        # Run verification
        try:
            if self.use_docker:
                return self._run_with_docker(query_input, len(names))
            else:
                return self._run_with_local_gnverifier(query_input, len(names))
        except Exception as e:
            self.logger.error(f"Error verifying names: {e}")
            # Return empty results for each name
            return [{} for _ in range(len(names))]
    
    def _run_with_docker(self, query_input: str, expected_count: int) -> List[Dict[str, Any]]:
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
        if self.config.data_sources:
            cmd.extend(["--sources", self.config.data_sources])
        
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
    
    def _run_with_local_gnverifier(self, query_input: str, expected_count: int) -> List[Dict[str, Any]]:
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
        
        if self.config.data_sources:
            cmd.extend(["--sources", self.config.data_sources])
        
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
    
    def process_query_groups(self, query_groups: List[QueryGroupRef], batch_size: int = 10000) -> Dict[str, Dict[str, Any]]:
        """Process a list of query groups in batches.
        
        Args:
            query_groups: List of query groups to process
            batch_size: Number of queries to process in each batch
            
        Returns:
            Dictionary mapping query group keys to verification results
        """
        # Extract query terms from each query group
        query_terms = [qg.query_term for qg in query_groups]
        query_group_keys = [qg.query_term for qg in query_groups]
        
        # Process in batches
        results = {}
        for i in range(0, len(query_terms), batch_size):
            batch_terms = query_terms[i:i+batch_size]
            batch_keys = query_group_keys[i:i+batch_size]
            
            self.logger.info(f"Processing batch {i//batch_size + 1} with {len(batch_terms)} queries")
            batch_results = self.verify_names(batch_terms)
            
            # Map results to query groups
            for key, result in zip(batch_keys, batch_results):
                # Validate response
                if self.validate_response(result):
                    results[key] = result
                else:
                    self.logger.warning(f"Invalid result for query term '{key}'")
                    results[key] = {}
        
        return results
