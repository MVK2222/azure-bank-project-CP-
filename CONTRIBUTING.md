# Contributing to Banking Data Platform

Thank you for your interest in contributing to the Banking Data Platform! This document provides guidelines and best practices for contributing to the project.

## Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Process](#development-process)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Code Review Guidelines](#code-review-guidelines)
- [Documentation Standards](#documentation-standards)
- [Security Considerations](#security-considerations)
- [Release Process](#release-process)

## Code of Conduct

### Our Commitment
We are committed to providing a welcoming and inclusive environment for all contributors. We expect all participants to:
- Be respectful and considerate in all interactions
- Accept constructive criticism gracefully
- Focus on what is best for the project and community
- Show empathy towards other community members

### Unacceptable Behavior
- Harassment, discrimination, or offensive comments
- Personal attacks or inflammatory language
- Publishing others' private information
- Any conduct that could reasonably be considered inappropriate

### Reporting Issues
If you experience or witness unacceptable behavior, please report it to [project maintainers contact].

## Getting Started

### Prerequisites
Before contributing, ensure you have:
1. Read the [DEVELOPMENT.md](docs/DEVELOPMENT.md) guide
2. Set up your local development environment
3. Familiarized yourself with the [ARCHITECTURE.md](docs/ARCHITECTURE.md)
4. Reviewed existing issues and pull requests

### Finding Ways to Contribute

#### Good First Issues
Look for issues labeled `good-first-issue` - these are suitable for newcomers:
- Documentation improvements
- Adding unit tests
- Fixing minor bugs
- Code cleanup and refactoring

#### Help Wanted
Issues labeled `help-wanted` indicate areas where we need assistance:
- Feature implementations
- Performance optimizations
- Integration improvements
- Advanced bug fixes

#### Suggesting Enhancements
Have an idea for improvement? Follow these steps:
1. Check if similar suggestion exists in issues
2. Create a new issue with label `enhancement`
3. Clearly describe the problem and proposed solution
4. Provide use cases and benefits
5. Wait for maintainer feedback before implementing

## Development Process

### 1. Fork and Clone
```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/azure-bank-project-CP-.git
cd azure-bank-project-CP-

# Add upstream remote
git remote add upstream https://github.com/MVK2222/azure-bank-project-CP-.git

# Verify remotes
git remote -v
```

### 2. Create a Branch
```bash
# Sync with upstream
git checkout main
git pull upstream main

# Create feature branch with descriptive name
git checkout -b feature/add-velocity-fraud-rule
# or
git checkout -b bugfix/fix-cosmos-retry-logic
# or
git checkout -b docs/update-architecture-diagram
```

**Branch Naming Conventions**:
- `feature/short-description` - New features
- `bugfix/short-description` - Bug fixes
- `hotfix/short-description` - Urgent production fixes
- `docs/short-description` - Documentation changes
- `refactor/short-description` - Code refactoring
- `test/short-description` - Test additions/improvements

### 3. Make Changes
Follow these guidelines while coding:
- Write clean, readable code
- Add comprehensive docstrings
- Include inline comments for complex logic
- Follow existing code style and patterns
- Keep changes focused and atomic

### 4. Test Your Changes
```bash
# Run unit tests
pytest tests/

# Run linter
flake8 functions/

# Format code
black functions/

# Test locally
cd functions
func start
# Upload test file and verify processing
```

### 5. Commit Your Changes
```bash
# Stage changes
git add .

# Commit with descriptive message
git commit -m "Add velocity-based fraud detection rule

- Implement sliding window algorithm for transaction counting
- Add configurable threshold via environment variable
- Include unit tests with edge cases
- Update documentation with rule details
- Performance: O(n log n) for sorted timestamps

Closes #123"
```

**Commit Message Format**:
```
<type>: <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code formatting (no logic changes)
- `refactor`: Code restructuring (no behavior changes)
- `test`: Adding or updating tests
- `perf`: Performance improvements
- `chore`: Build/tooling changes

**Example**:
```
feat: Add geo-location fraud detection rule

Implement impossible travel detection for transactions occurring
in different cities within a short timeframe. Uses haversine 
formula to calculate distance and estimates minimum travel time.

- Add geopy dependency for distance calculation
- Configure 10-minute threshold (adjustable)
- Handle missing location data gracefully
- Add comprehensive test suite
- Document false positive scenarios

Closes #45
```

### 6. Push and Create Pull Request
```bash
# Push to your fork
git push origin feature/add-velocity-fraud-rule

# Go to GitHub and create Pull Request
# Fill in PR template with all required information
```

## Coding Standards

### Python Style Guide
Follow PEP 8 with these additions:
- **Line length**: 120 characters (not 79)
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Double quotes for strings, single for characters
- **Imports**: Group by standard library, third-party, local
- **Docstrings**: Google style with type hints

### Docstring Format
```python
def process_transaction(row: dict, source_type: str) -> tuple[list, dict]:
    """
    Validate and transform a single transaction row.
    
    This function applies schema validation and business rules to ensure
    data quality before Cosmos DB insertion. Invalid data is quarantined
    for manual review.
    
    Args:
        row (dict): Raw CSV row as dictionary with string values
        source_type (str): Transaction type ("ATM" or "UPI")
    
    Returns:
        tuple: (error_list, cleaned_row)
            error_list (list[str]): Validation errors, empty if valid
            cleaned_row (dict): Normalized row with typed values
    
    Raises:
        ValueError: If source_type is not recognized
    
    Example:
        >>> row = {"TransactionID": "TXN001", "Amount": "5000"}
        >>> errors, cleaned = process_transaction(row, "ATM")
        >>> assert len(errors) == 0
        >>> assert cleaned["Amount"] == 5000.0
    
    Note:
        This function does not handle Cosmos DB insertion - that is
        done by the calling processor module.
    
    TODO: Add support for international transaction codes
    """
    pass
```

### Naming Conventions
- **Functions**: `snake_case` (e.g., `validate_transaction_row`)
- **Classes**: `PascalCase` (e.g., `FraudDetectionEngine`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `HIGH_VALUE_THRESHOLD`)
- **Private**: Leading underscore (e.g., `_sanitize_for_cosmos`)
- **Module variables**: `_lowercase_with_underscore` (e.g., `_blob_client`)

### Code Organization
- **Module imports**: Standard lib, third-party, local (separated by blank line)
- **Module docstring**: At top of file explaining purpose
- **Constants**: After imports, before functions
- **Functions**: Public before private
- **Main logic**: At bottom, guarded by `if __name__ == "__main__"`

### Error Handling
```python
# GOOD: Specific exceptions with context
try:
    result = cosmos_container.upsert_item(item)
except CosmosHttpResponseError as e:
    logging.error(f"Cosmos DB upsert failed for item {item['id']}: {e}")
    raise

# BAD: Bare except or generic exception
try:
    result = cosmos_container.upsert_item(item)
except:  # BAD - catches everything
    logging.error("Something failed")
```

### Logging Guidelines
```python
# Use appropriate log levels
logging.debug("Detailed diagnostic information")
logging.info("General informational messages")
logging.warning("Recoverable issues (bad data, retries)")
logging.error("Unrecoverable errors requiring attention")

# Include context in log messages
logging.info(f"Processing {file_name}, source_type={source_type}, rows={len(rows)}")

# Use structured logging for parsing
logging.info(f"Processing completed: file={file_name}, valid={valid_count}, invalid={invalid_count}, alerts={alert_count}")

# Don't log sensitive data
# BAD
logging.info(f"Card number: {card_number}")
# GOOD
logging.info(f"Card number: {card_number[:4]}****")
```

## Testing Requirements

### Test Coverage
All new code must include tests:
- **Unit tests**: 80%+ coverage for new functions
- **Integration tests**: For new features end-to-end
- **Edge cases**: Empty input, invalid data, boundary conditions

### Test Structure
```python
# tests/test_validators.py
import pytest
from BatchIngestionFunction.validator.transaction_validator import validate_transaction_row


class TestTransactionValidator:
    """Test suite for transaction validation logic."""
    
    def test_valid_transaction_happy_path(self):
        """Test valid transaction with all required fields."""
        row = {
            "TransactionID": "TXN001",
            "Amount": "5000",
            "Timestamp": "2024-01-01T10:00:00Z"
        }
        errors, cleaned = validate_transaction_row(row, "ATM")
        
        assert len(errors) == 0, "Should have no errors"
        assert cleaned["Amount"] == 5000.0, "Amount should be float"
        assert "Timestamp" in cleaned, "Timestamp should be present"
    
    def test_missing_transaction_id(self):
        """Test validation fails when TransactionID is missing."""
        row = {"Amount": "5000", "Timestamp": "2024-01-01T10:00:00Z"}
        errors, cleaned = validate_transaction_row(row, "ATM")
        
        assert "Missing TransactionID" in errors
    
    def test_invalid_amount_format(self):
        """Test validation handles non-numeric amount."""
        row = {
            "TransactionID": "TXN001",
            "Amount": "not-a-number",
            "Timestamp": "2024-01-01T10:00:00Z"
        }
        errors, cleaned = validate_transaction_row(row, "ATM")
        
        assert any("Amount" in err for err in errors)
    
    @pytest.mark.parametrize("amount,expected", [
        ("1,000", 1000.0),
        ("1000.50", 1000.5),
        ("  1000  ", 1000.0),
    ])
    def test_amount_normalization(self, amount, expected):
        """Test amount parsing handles various formats."""
        row = {
            "TransactionID": "TXN001",
            "Amount": amount,
            "Timestamp": "2024-01-01T10:00:00Z"
        }
        errors, cleaned = validate_transaction_row(row, "ATM")
        
        assert cleaned["Amount"] == expected
```

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=functions --cov-report=html

# Run specific test file
pytest tests/test_validators.py

# Run specific test
pytest tests/test_validators.py::TestTransactionValidator::test_valid_transaction_happy_path

# Run tests matching pattern
pytest -k "validator"

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Test Data
- Use `test_data/` directory for sample CSV files
- Keep test files small (<100 rows)
- Include edge cases (empty files, malformed data)
- Don't commit real customer data (PII)

## Pull Request Process

### Before Submitting PR
- [ ] All tests pass locally
- [ ] Code follows style guidelines (flake8, black)
- [ ] Docstrings added for all public functions
- [ ] Unit tests added for new functionality
- [ ] Documentation updated (if needed)
- [ ] Commit messages follow format
- [ ] Branch is up-to-date with main

### PR Template
When creating a PR, fill in this template:

```markdown
## Description
Brief description of changes and motivation.

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to break)
- [ ] Documentation update

## Related Issue
Closes #123

## Changes Made
- Added velocity-based fraud detection rule
- Implemented sliding window algorithm
- Added unit tests with edge cases
- Updated documentation

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass (if applicable)
- [ ] Manually tested locally
- [ ] Tested with production-like data

## Screenshots (if applicable)
[Add screenshots of UI changes or monitoring dashboards]

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] All tests pass
- [ ] No new warnings or errors

## Additional Notes
Any additional context or considerations for reviewers.
```

### PR Review Cycle
1. **Submit PR**: Fill in template completely
2. **Automated checks**: CI/CD runs tests and linting
3. **Code review**: Maintainer reviews within 2 business days
4. **Address feedback**: Make requested changes
5. **Re-review**: Maintainer re-reviews changes
6. **Approval**: PR approved by at least one maintainer
7. **Merge**: Maintainer merges to main

### After Merge
```bash
# Sync your fork with upstream
git checkout main
git pull upstream main
git push origin main

# Delete feature branch
git branch -d feature/add-velocity-fraud-rule
git push origin --delete feature/add-velocity-fraud-rule
```

## Code Review Guidelines

### For Contributors
When your PR is under review:
- Respond to feedback within 2 business days
- Be open to suggestions and constructive criticism
- Explain your reasoning if you disagree with feedback
- Make requested changes or provide justification
- Mark conversations as resolved once addressed
- Request re-review after making changes

### For Reviewers
When reviewing PRs:
- Review within 2 business days
- Be respectful and constructive
- Focus on code quality, not personal preferences
- Explain the "why" behind feedback
- Approve PRs that meet standards
- Request changes clearly with actionable items

### Code Review Checklist

#### Functionality
- [ ] Code does what it claims to do
- [ ] Edge cases are handled
- [ ] Error handling is appropriate
- [ ] No obvious bugs or logic errors

#### Design
- [ ] Code is well-organized and modular
- [ ] Functions have single responsibility
- [ ] Reusable components are extracted
- [ ] No code duplication

#### Readability
- [ ] Code is easy to understand
- [ ] Variable/function names are descriptive
- [ ] Complex logic has comments
- [ ] Docstrings are comprehensive

#### Performance
- [ ] No obvious performance issues
- [ ] Database queries are optimized
- [ ] Loops and iterations are efficient
- [ ] Memory usage is reasonable

#### Security
- [ ] No hardcoded secrets or credentials
- [ ] Input validation is present
- [ ] No SQL injection or XSS vulnerabilities
- [ ] PII is handled appropriately

#### Testing
- [ ] Tests cover new functionality
- [ ] Edge cases are tested
- [ ] Tests are clear and maintainable
- [ ] All tests pass

#### Documentation
- [ ] README updated if needed
- [ ] API documentation added
- [ ] Inline comments for complex logic
- [ ] Docstrings follow format

## Documentation Standards

### Code Documentation
- **Module docstring**: Explain module purpose and responsibilities
- **Function docstring**: Args, returns, raises, examples
- **Inline comments**: Explain "why", not "what"
- **Type hints**: Use for function parameters and returns

### README Updates
Update README.md when:
- Adding new features
- Changing configuration
- Adding dependencies
- Modifying setup process

### Documentation Files
Update docs/ when:
- Architecture changes (ARCHITECTURE.md)
- New development steps (DEVELOPMENT.md)
- New deployment procedures (DEPLOYMENT.md)
- Security changes (SECURITY.md)

### Comment Quality
```python
# GOOD: Explains reasoning and context
# Use exponential backoff to handle Cosmos DB throttling (429 errors).
# Without backoff, rapid retries would worsen throttling.
sleep_time = base_delay * (2 ** attempt)

# BAD: States the obvious
# Multiply base_delay by 2 to the power of attempt
sleep_time = base_delay * (2 ** attempt)
```

## Security Considerations

### Never Commit
- Connection strings or API keys
- Passwords or access tokens
- Customer data (PII)
- Private keys or certificates
- Internal IP addresses or URLs

### Code Security
- **Input validation**: Validate all external inputs
- **SQL injection**: Use parameterized queries
- **XSS prevention**: Sanitize output
- **Secrets management**: Use environment variables or Key Vault
- **Least privilege**: Request minimum required permissions

### Reporting Security Issues
If you discover a security vulnerability:
1. **DO NOT** open a public issue
2. Email security contact: [maintainer email]
3. Include detailed description and steps to reproduce
4. Allow time for fix before public disclosure

## Release Process

### Semantic Versioning
We follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

Example: `1.2.3`
- `1` = Major version
- `2` = Minor version
- `3` = Patch version

### Release Workflow
1. **Version bump**: Update version in relevant files
2. **Changelog**: Update CHANGELOG.md with release notes
3. **Testing**: Comprehensive testing in staging environment
4. **Tag**: Create Git tag (e.g., `v1.2.3`)
5. **Deploy**: Deploy to production via CI/CD
6. **Announce**: Notify team of release

### Changelog Format
```markdown
## [1.2.3] - 2024-01-15

### Added
- Velocity-based fraud detection rule
- Geo-location fraud detection

### Changed
- Improved Cosmos DB retry logic with exponential backoff
- Updated documentation for new fraud rules

### Fixed
- Fixed date parsing for European date formats
- Resolved memory leak in CSV processing

### Deprecated
- Old fraud detection API (use new API in v2.0)

### Removed
- Legacy CSV parser (replaced with improved version)

### Security
- Updated azure-cosmos dependency to fix CVE-XXXX-XXXXX
```

## Questions and Support

### Getting Help
- **Documentation**: Check docs/ directory first
- **Issues**: Search existing issues on GitHub
- **Discussions**: Use GitHub Discussions for questions
- **Slack**: Internal team channel #data-platform
- **Email**: [maintainer contact]

### Office Hours
Maintainers available for questions:
- **Time**: Tuesdays 2-3 PM IST
- **Location**: Virtual meeting link in team calendar
- **Format**: Open Q&A, bring your questions

---

## Thank You!

We appreciate your contribution to making the Banking Data Platform better! Every contribution, no matter how small, makes a difference.

**Happy Coding! 🚀**
