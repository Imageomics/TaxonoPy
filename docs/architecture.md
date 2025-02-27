# TaxonoPy Architecture

This document outlines the architectural design rationale of the TaxonoPy package.


## Core Principles

The package design is guided by:

1. **Immutability**: Core data structures are immutable to prevent accidental modification and ensure data integrity throughout processing.
2. **Clear Data Flow**: The resolution process follows a staged progression from raw inputs to resolved outputs.
3. **Separation of Concerns**: Each module has a single, well-defined responsibility.
4. **Reference-based Relationships**: Objects refer to each other by ID or ID groups rather than embedding for data normalization.
5. **Type Safety**: Attempt for comprehensive type annotations throughout the codebase enhance readability and enable static type checking.

## Package Structure
```
TaxonoPy
├── api_specs/                    # API specifications
│   └── gnverifier_openapi.json
├── docs/
│   └── architecture.md           # This design overview
├── scripts/                      # Utility scripts
│   └── generate_gnverifier_types.py
├── src
│   └── taxonopy/                 # Main package
│       ├── types/                # Data models and types
│       │   ├── data_classes.py
│       │   ├── gnverifier.py     # Generated API types
│       │   └── __init__.py
│       ├── cli.py                # Command-line interface
│       ├── logging_config.py     # Logging configuration
│       ├── resolution_attempt_manager.py # Logic to manage resolution attempts
│       ├── __init__.py           # Package initialization
│       └── __main__.py           # Entry point
├── pyproject.toml
└── README.md
```

## Core Components

### 1. Data Model

The core data model is defined in `src/taxonopy/types/data_classes.py`.

Input data is expected to be tabular (CSV or Parquet) following the metadata schema for taxonomic labels establised for the TreeOfLife dataset. Each entry here is represented by a `TaxonomicEntry` object.

- **TaxonomicEntry**: Represents a single taxonomic entry from the input data, containing taxonomic ranks, names, and metadata.
- **EntryGroupRef**: Groups taxonomic entries with identical taxonomic data to minimize API calls.
- **QueryGroupRef**: Groups entry groups that will use the same query term for resolution.
- **ResolutionAttempt**: Records the result of a GNVerifier query and its interpretation.
- **ResolutionStatus (Enum)**: Represents the possible states of a resolution attempt, from initial processing to final resolution.

These classes form a progression that represents the staged transformation of data through the resolution workflow:

```
Input Data → TaxonomicEntry → EntryGroupRef → QueryGroupRef → ResolutionAttempt → Resolved Output
```

### 2. Resolution Attempt Manager

The `ResolutionAttemptManager` provides a centralized mechanism for managing resolution attempts:

- **Attempt Creation**: Generates unique identifiers for attempts and maintains links between related attempts
- **Attempt Tracking**: Stores attempts and provides methods for retrieving them by ID or query group
- **Chain Management**: Allows traversal of the full history of attempts for a query group
- **Status Tracking**: Provides methods for determining which query groups need retries or have been successfully resolved
- **Statistics**: Gathers statistics about the resolution process

This component is critical for implementing retry strategies and maintaining the full provenance of the resolution process.

### 3. Command-Line Interface

The CLI is defined in `src/taxonopy/cli.py` and provides a user-friendly interface to the resolution functionality. It uses Python's standard `argparse` library to parse command-line arguments and options.

Entry into the CLI is via `__main__.py`, which sets up the environment and calls the `main()` function from `cli.py`.

### 4. Logging Configuration

Logging is centralized in `src/taxonopy/logging_config.py`, which provides a consistent logging setup across the package.

### 5. API Type Generation

The package includes automation for generating Python types from the GNVerifier OpenAPI specification:

- `api_specs/gnverifier_openapi.json`: The OpenAPI specification for the GNVerifier API.
- `scripts/generate_gnverifier_types.py`: A script that generates Python type definitions from the OpenAPI spec.
- `src/taxonopy/types/gnverifier.py`: The generated Python types for interacting with the GNVerifier API.

## Data Flow

The resolution process follows a staged progression:

1. **Input Parsing**: Input data (Parquet files) is parsed into `TaxonomicEntry` objects.
2. **Entry Grouping**: Entries with identical taxonomic data are grouped into `EntryGroupRef` objects.
3. **Query Planning**: Entry groups are organized into `QueryGroupRef` objects based on their query terms.
4. **Query Execution**: Queries are sent to the GNVerifier API, with results stored in `ResolutionAttempt` objects.
5. **Resolution**: Results are interpreted to produce a standardized taxonomy.
6. **Output Generation**: Resolved taxonomies are written to output files.

## Future Components

The following components are planned for future development:

1. **Input Parser**: Will handle reading and parsing taxonomic data from various formats.
2. **Entry Grouper**: Will implement the logic for grouping identical taxonomic entries.
3. **Query Planner**: Will determine the optimal strategy for resolving entries.
4. **GNVerifier Client**: Will handle communication with the GNVerifier API.
5. **Resolution Handler**: Will interpret API responses and apply resolution rules.
6. **Output Generator**: Will format and write resolved taxonomies to output files.

## Design Decisions

### Immutable Data Classes

All core data classes are implemented as frozen dataclasses to ensure immutability. This design choice:
- Prevents accidental modification of data
- Makes objects thread-safe
- Enables efficient caching
- Simplifies debugging

### Reference-based Relationships

Instead of embedding objects within each other, relationships are maintained through references (IDs/keys). This approach:
- Reduces memory usage
- Avoids circular references
- Follows data normalization principles

### Support for Iteration and Retries

The data model is specifically designed to support iterative resolution and retry scenarios through a linked-list approach:

- **ResolutionStatus Enum**: Includes statuses that track the progression of resolution attempts, including states that indicate the need for further processing.
  
- **Hierarchical Query Approach**: The model supports trying multiple taxonomic ranks when resolving an entry, starting with the most specific and falling back to higher ranks as needed.

- **Single Parent Reference**: Each `ResolutionAttempt` includes a `previous_attempt_id` field that references its immediate predecessor, creating a linked-list structure of resolution attempts. This design:
  - Forms a clean chain of attempts that can be traversed to reconstruct the full history
  - Avoids redundant storage of the entire history in each attempt
  - Follows proper reference-based design principles
  - Models the sequential nature of resolution attempts

- **Timestamp Recording**: Each resolution attempt records when it occurred, enabling time-based analysis and processing of retries.

- **Metadata Dictionary**: Flexible storage for additional data about resolution attempts, which can include information about retry strategies, confidence scores, and resolution decisions.

Example retry chain:
1. Initial attempt (id: "a1"): Uses species level `Turdus migratorius` → No match
   - `previous_attempt_id = None`
2. First retry (id: "a2"): Uses genus level `Turdus` → No match
   - `previous_attempt_id = "a1"`
3. Second retry (id: "a3"): Uses class level `Aves` → Match found
   - `previous_attempt_id = "a2"`

To reconstruct the full history, one would traverse the chain by following the `previous_attempt_id` references, similar to how git commits or other version control systems track history.

This linked-list approach allows TaxonoPy to handle the complexities of taxonomic resolution where first attempts often fail due to spelling variations, taxonomic revisions, or incomplete data, while maintaining a clean, efficient data model

### Separation of CLI and Core Logic

The command-line interface is kept separate from the core resolution logic. This separation:
- Enables programmatic use of the package
- Simplifies testing
- Allows for future alternate interfaces (e.g., GUI, web API)

## Testing Strategy

The package includes a testing framework that grows with the implementation:

1. **Unit Tests**: Test individual components in isolation.
2. **Integration Tests**: Test interactions between components.
3. **Mocking**: Use mocks to isolate components from external dependencies.
4. **Fixtures**: Provide standardized test data.

## Extension Points

TaxonoPy is designed with several extension points for future development:

1. **Additional Resolvers**: Support for alternative taxonomic resolution services.
2. **Custom Resolution Strategies**: Pluggable strategies for resolving taxonomic names.
3. **Input/Output Formats**: Support for additional file formats beyond Parquet.
4. **Resolution Rules**: Configurable rules for taxonomic standardization.
