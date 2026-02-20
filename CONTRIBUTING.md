# Contributing to sovereign-seal

## Core Principle

This library has one job: halt when integrity fails. Contributions should make that job more reliable, more portable, or more testable. Not more complex.

## How to Contribute

### Bug Reports

Open an issue with:
- Python version
- OS
- Minimal reproduction steps
- Expected vs actual behavior

### Pull Requests

1. Fork the repo
2. Create a branch (`git checkout -b fix/your-fix`)
3. Make your change
4. Run the test suite: `python -m unittest tests.test_adversarial -v`
5. All 15 tests must pass
6. Submit PR with a clear description

### What We Want

- **More adversarial tests** — Find a way to break it that we haven't tested
- **Framework adapters** — LangChain, CrewAI, AutoGen, Haystack wrappers
- **Performance benchmarks** — How fast is verify() at 10K, 100K, 1M entries?
- **Distributed witness protocols** — Network-based witness sync
- **Documentation** — Better examples, tutorials, integration guides

### What We Don't Want

- Dependencies (the zero-dependency constraint is non-negotiable)
- "Warn and continue" modes (halt is the feature)
- Complexity for complexity's sake

## Code Style

- Standard library only
- Type hints encouraged
- Docstrings on all public methods
- Tests for all new behavior

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
