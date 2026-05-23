"""Cooperative cancellation primitive shared by pipeline stages.

The GUI sets a `threading.Event` when the user clicks "Detener"; each stage
(download, crop, PDF generation) polls it between safe checkpoints and raises
`Cancelled` to unwind the pipeline.
"""


class Cancelled(Exception):
    """Raised when a pipeline stage observes a set cancel event."""
