"""Architecture enforcement tests.

These tests use AST scanning and import-graph analysis to enforce structural
boundaries — for example that the workflow/state-machine layer never imports
or references SQLite internals.
"""
