import os
import shutil
import subprocess
from pathlib import Path
import filecmp
from tempfile import NamedTemporaryFile

# Constants
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TYPES_DIR = PROJECT_ROOT / "src/taxonopy/types"
API_SPECS_DIR = PROJECT_ROOT / "api_specs"

OPENAPI_URL = "https://apidoc.globalnames.org/static/gnames/openapi.json"
SPEC_FILE = API_SPECS_DIR / "gnverifier_openapi.json"
SPEC_FILE_NEW = API_SPECS_DIR / "gnverifier_openapi.json.new"
TYPES_FILE = TYPES_DIR / "gnverifier.py"
TYPES_FILE_NEW = TYPES_DIR / "gnverifier.py.new"

# Ensure directories exist
TYPES_DIR.mkdir(parents=True, exist_ok=True)
API_SPECS_DIR.mkdir(parents=True, exist_ok=True)

# Helper functions
def download_spec(file_path):
    """Download the OpenAPI spec to the specified file."""
    subprocess.run(["curl", "-s", OPENAPI_URL, "-o", str(file_path)], check=True)

def generate_types(input_spec, output_file):
    """Generate Python types from an OpenAPI spec."""
    subprocess.run([
        "datamodel-codegen",
        "--force-optional", # e.g. dataSourcesNum is listed as required in the OpenAPI spec but it is not included in API responses
        "--input", str(input_spec),
        "--output", str(output_file),
        "--target-python-version", "3.9",
        "--snake-case-field",
        "--output-model-type", "pydantic_v2.BaseModel"
    ], check=True)

def normalize_file(file_path):
    """Normalize the file by removing timestamp and standardizing filename."""
    with open(file_path, "r") as infile, NamedTemporaryFile(delete=False, mode="w") as temp_file:
        for line in infile:
            if line.startswith("#   timestamp:"):
                continue
            if line.startswith("#   filename:"):
                temp_file.write("#   filename:  gnverifier_openapi.json\n")
            else:
                temp_file.write(line)
    return Path(temp_file.name)

def compare_files(file1, file2):
    """Compare two files after normalization."""
    norm1 = normalize_file(file1)
    norm2 = normalize_file(file2)
    result = filecmp.cmp(norm1, norm2, shallow=False)
    os.unlink(norm1)
    os.unlink(norm2)
    return result

def main():
    if not SPEC_FILE.exists() and not TYPES_FILE.exists():
        print("No existing spec or types file found. Downloading and generating types...")
        download_spec(SPEC_FILE)
        generate_types(SPEC_FILE, TYPES_FILE)
        print("Spec and types generated successfully.")
        return

    if SPEC_FILE.exists() and not TYPES_FILE.exists():
        print("Spec file exists but no types file. Generating types...")
        generate_types(SPEC_FILE, TYPES_FILE)

    if not SPEC_FILE.exists() and TYPES_FILE.exists():
        print("Types file exists but no spec file. Downloading new spec...")
        download_spec(SPEC_FILE_NEW)
        generate_types(SPEC_FILE_NEW, TYPES_FILE_NEW)
        if compare_files(TYPES_FILE, TYPES_FILE_NEW):
            print("No material changes detected. Saving new spec...")
            SPEC_FILE_NEW.rename(SPEC_FILE)
            TYPES_FILE_NEW.unlink()
        else:
            print("Material changes detected! Review the differences:")
            print(f"New spec: {SPEC_FILE_NEW}")
            print(f"New types: {TYPES_FILE_NEW}")
        return

    if SPEC_FILE.exists() and TYPES_FILE.exists():
        print("Both spec and types files exist. Checking for updates...")
        download_spec(SPEC_FILE_NEW)
        generate_types(SPEC_FILE_NEW, TYPES_FILE_NEW)
        if compare_files(TYPES_FILE, TYPES_FILE_NEW):
            print("No material changes detected. Cleaning up...")
            SPEC_FILE_NEW.unlink()
            TYPES_FILE_NEW.unlink()
        else:
            print("Material changes detected! Review the differences:")
            print(f"New spec: {SPEC_FILE_NEW}")
            print(f"New types: {TYPES_FILE_NEW}")

if __name__ == "__main__":
    main()
