# src/core/exceptions.py
class PipelineError(Exception):
    """Base exception for all pipeline errors."""
    pass

class IngestionError(PipelineError):
    """Raised when a source cannot be fetched."""
    pass

class ParsingError(PipelineError):
    """Raised when RSS/HTML parsing fails."""
    pass

class TemporalFilterError(PipelineError):
    """Raised when date parsing fails critically."""
    pass

class PlaywrightNotInstalledError(PipelineError):
    """Raised if Playwright browsers are missing."""
    pass