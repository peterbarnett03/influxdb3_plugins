# Style Guidelines for influxdb3_plugins Repository

## Purpose
Apply consistent documentation standards to the example plugins repository.

## File Organization

### Directory Structure
```
plugin_name/
├── README.md
├── plugin_name.py
├── config.py
├── test/
│   ├── test_plugin_name.py
│   └── fixtures/
└── examples/
    └── example_config.yaml
```

### File Naming
- Use snake_case for Python files
- Use kebab-case for documentation files
- Use descriptive names that match functionality

## README Structure

### Required Sections
Each plugin README should include:

1. **Plugin Name** (h1)
2. **Description** - Brief overview of functionality
3. **Configuration** - All configuration parameters
4. **Requirements** - Dependencies and prerequisites
5. **Trigger Setup** - How to configure triggers
6. **Example Usage** - Working examples with expected output
7. **Code Overview** - Walkthrough of key functions
8. **Troubleshooting** - Common issues and solutions

### Configuration Documentation
- Document all parameters with types and defaults
- Use tables for complex configurations
- Include examples for each parameter

**Example:**
```markdown
## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database` | string | required | Target database name |
| `batch_size` | integer | 1000 | Maximum records per batch |
| `timeout` | integer | 30 | Connection timeout in seconds |
```

### Example Usage Format
- Provide complete, working examples
- Show expected input and output
- Include error handling examples

**Example:**
```markdown
## Example Usage

### Basic Usage
```python
from plugins.example_plugin import ExamplePlugin

plugin = ExamplePlugin({
    'database': 'my_database',
    'batch_size': 500
})

result = plugin.process(data)
```

### Expected Output
```json
{
  "success": true,
  "records_processed": 500,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Voice, tone, and grammar
- Use Google Developer Documentation style
- Use active voice--state who or what is performing the action
- Use present tense
- Use simple, clear language
- Avoid jargon and complex terminology
- Use second person ("you") for instructions
- Use third person for general descriptions

## Markdown Style Guidelines

### Semantic Line Feeds
- Use semantic line feeds (one sentence per line)
- Break lines at natural language boundaries
- This improves diff readability and makes editing easier

**Example:**
```markdown
This is the first sentence.
This is the second sentence that continues the paragraph.
```

### Heading Structure
- Use h2-h6 headings in content (h1 comes from title)
- Use sentence case for headings
- Don't skip heading levels

**Example:**
```markdown
## Configuration parameters
### Required parameters
#### Database connection
```

### Code Block Formatting
- Format code examples to fit within 80 characters
- Use long options in command line examples (`--option` instead of `-o`)
- Include proper syntax highlighting

**Example:**
```bash
influxdb3 write \
  --database DATABASE_NAME \
  --token AUTH_TOKEN \
  --precision ns
```

### File and Directory References
- Use backticks for file names and paths
- Use forward slashes for paths (even on Windows)

**Example:**
```markdown
Edit the `config.py` file in the `plugins/` directory.
```

## Code Documentation Standards

### Python Docstrings
- Use triple quotes for docstrings
- Follow Google docstring style
- Include type hints where possible

**Example:**
```python
def process_data(data: dict, config: dict) -> bool:
    """Process incoming data using the provided configuration.
    
    Args:
        data: The incoming data dictionary
        config: Plugin configuration parameters
        
    Returns:
        True if processing succeeded, False otherwise
        
    Raises:
        ValueError: If required configuration is missing
    """
```

### Comments
- Use inline comments to explain complex logic
- Avoid obvious comments
- Explain the "why" not the "what"

**Example:**
```python
# Convert timestamp to nanoseconds for InfluxDB compatibility
timestamp_ns = int(timestamp * 1e9)
```

## Placeholder Conventions

### Use UPPERCASE for placeholders
```bash
influxdb3 write --database DATABASE_NAME --token AUTH_TOKEN
```

### Placeholder Descriptions
- Don't use pronouns ("your", "this")
- Be specific about data types and formats
- Provide examples for complex formats

**Example:**
```markdown
Replace the following:
- `DATABASE_NAME`: the name of the database to write to
- `AUTH_TOKEN`: a database token with write permissions
```

## Links and References

### Internal Links
- Use relative paths for internal repository links
- Use descriptive link text

**Example:**
```markdown
See the [configuration guide](./docs/configuration.md) for details.
```

### External Links
- Use full URLs for external references
- Include link text that describes the destination

**Example:**
```markdown
For more information, see the [InfluxDB 3 documentation](https://docs.influxdata.com/influxdb3/).
```

## Testing Documentation

### Test Example Format
```python
def test_plugin_basic_functionality():
    """Test basic plugin functionality with mock data."""
    # Test implementation
    pass
```

### Test Documentation
- Document what each test validates
- Include setup and teardown requirements
- Provide examples of test data

## Error Handling

### Error Messages
- Use clear, actionable error messages
- Include suggested solutions
- Provide context about the error

**Example:**
```python
raise ValueError(
    f"Database '{database_name}' not found. "
    f"Check the database name and ensure it exists."
)
```

## Commit Message Format

### Use conventional commits
```
type(scope): description

feat(plugin): add new data transformation plugin
fix(docs): correct configuration parameter description
docs(readme): update installation instructions
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Test changes
- `chore`: Maintenance tasks

_These standards are extracted from the [InfluxData Documentation guidelines](https://github.com/influxdata/docs-v2/blob/master/CONTRIBUTING.md)._