"""Property-based testing configuration.

Shared settings and markers for all PBT tests. Each design property maps to
exactly one @given test file. Tests use at least 100 examples with a 5-second
deadline per example.
"""

from hypothesis import settings

# Default PBT profile: 100 examples minimum, 5s deadline
settings.register_profile(
    "default",
    max_examples=100,
    deadline=5000,
)
settings.register_profile(
    "ci",
    max_examples=200,
    deadline=10000,
)
settings.load_profile("default")
