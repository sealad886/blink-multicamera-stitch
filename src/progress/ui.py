"""Rich layout components for the blink-multicamera-stitch progress system.

This module provides components for displaying pipeline progress, system resources,
and error information in a rich, interactive interface.
"""

from datetime import datetime, timedelta
import humanize
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
)
from rich.text import Text
from progress.state import PipelineState

class StageProgress:
    """Component for displaying the progress of a single pipeline stage."""

    def __init__(self, stage_name: str, state: PipelineState):
        """Initialize the StageProgress component.

        Args:
            stage_name: Name of the pipeline stage
            state: PipelineState instance for tracking stage progress
        """
        self.stage_name = stage_name
        self.state = state
        self.progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            transient=True
        )
        self.task_id = self.progress.add_task(
            description=f"[bold]{stage_name}[/bold]",
            start=False,
            total=100
        )
        self.start_time = None
        self.end_time = None

    def update(self) -> RenderableType:
        """Update the progress display based on current state.

        Returns:
            RenderableType containing the updated progress display
        """
        stage_status = self.state.get_stage_status(self.stage_name)

        if not stage_status:
            return Panel(
                Text(f"Stage {self.stage_name} not started yet"),
                title=f"[bold]{self.stage_name}[/bold]",
                border_style="blue"
            )

        status = stage_status.get("status", "unknown")
        progress = stage_status.get("progress", 0.0)
        start_time_str = stage_status.get("start_time")
        end_time_str = stage_status.get("end_time")

        # Update start/end times
        if start_time_str and not self.start_time:
            self.start_time = datetime.fromisoformat(start_time_str)
        if end_time_str and not self.end_time:
            self.end_time = datetime.fromisoformat(end_time_str)

        # Update progress bar
        self.progress.update(
            self.task_id,
            completed=int(progress * 100),
            total=100,
            visible=True
        )

        # Create status message
        status_text = Text(f"Status: {status.capitalize()}", style="bold")

        if status == "completed":
            if self.start_time and self.end_time:
                duration = humanize.precisedelta(
                    self.end_time - self.start_time
                )
                status_text.append(f" (Completed in {duration})")
            status_text.stylize("green")
        elif status == "failed":
            status_text.stylize("red")
        elif status == "running":
            status_text.stylize("yellow")

        # Create progress information
        progress_info = Table.grid(padding=0)
        progress_info.add_row(status_text)
        progress_info.add_row(Text(f"Progress: {progress:.1%}"))

        if self.start_time:
            progress_info.add_row(Text(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}"))
        if self.end_time:
            progress_info.add_row(Text(f"Ended: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}"))

        # Add duration if completed
        if status == "completed" and self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            progress_info.add_row(Text(f"Duration: {humanize.precisedelta(timedelta(seconds=duration))}"))

        return Panel(
            self.progress,
            title=f"[bold]{self.stage_name}[/bold]",
            border_style="blue"
        )

class SystemResourcePanel:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def add_stage(self, name):
        pass

    def update_stage(self, name, status, progress, *args, **kwargs):
        pass

    def add_error(self, severity, message, stage):
        pass
class Dashboard:
    """Minimal Dashboard stub for pipeline integration."""
    def __init__(self, state):
        self.state = state
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    def add_stage(self, name):
        pass
    def update_stage(self, name, status, progress, *args, **kwargs):
        pass
    def add_error(self, severity, message, stage):
        pass
    """Component for displaying system resource utilization."""
