"""State persistence module for the blink-multicamera-stitch progress system.

This module provides JSON-backed state persistence for tracking pipeline progress,
automatic recovery/resumption capabilities, and historical performance metrics.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import logging
from loguru import logger

# Configure logging
logger.add("progress.log", rotation="10 MB")

class PipelineState:
    """Manages the state of the pipeline execution with persistence and recovery."""

    def __init__(self, state_file: str = "pipeline_state.json"):
        """Initialize the PipelineState with a state file path.

        Args:
            state_file: Path to the JSON state file
        """
        self.state_file = Path(state_file)
        self._state: Dict[str, Any] = {
            "stages": {},
            "metrics": {},
            "last_run": None,
            "recovery_point": None,
            "history": []
        }

    def load_or_create(self) -> 'PipelineState':
        """Load existing state or create a new one if none exists.

        Returns:
            The initialized PipelineState instance
        """
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    self._state = json.load(f)
                logger.info(f"Loaded state from {self.state_file}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load state: {e}. Creating new state.")
                self._state = {
                    "stages": {},
                    "metrics": {},
                    "last_run": None,
                    "recovery_point": None,
                    "history": []
                }
        else:
            logger.info(f"Creating new state at {self.state_file}")

        return self

    def save(self) -> None:
        """Save the current state to the state file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self._state, f, indent=2)
            logger.info(f"Saved state to {self.state_file}")
        except IOError as e:
            logger.error(f"Failed to save state: {e}")

    def update_stage(self, stage_name: str, status: str, progress: float = 0.0,
                    start_time: Optional[datetime] = None,
                    end_time: Optional[datetime] = None) -> None:
        """Update the status of a pipeline stage.

        Args:
            stage_name: Name of the stage to update
            status: Current status of the stage (e.g., 'running', 'completed', 'failed')
            progress: Progress percentage (0.0 to 1.0)
            start_time: Optional datetime when the stage started
            end_time: Optional datetime when the stage ended
        """
        if stage_name not in self._state["stages"]:
            self._state["stages"][stage_name] = {}

        self._state["stages"][stage_name].update({
            "status": status,
            "progress": progress,
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None
        })

        # Update metrics if stage is completed
        if status == "completed" and start_time and end_time:
            duration = (end_time - start_time).total_seconds()
            self._state["metrics"][stage_name] = {
                "duration": duration,
                "completion_time": end_time.isoformat()
            }

        self.save()

    def get_stage_status(self, stage_name: str) -> Dict[str, Any]:
        """Get the status of a specific stage.

        Args:
            stage_name: Name of the stage to query

        Returns:
            Dictionary containing the stage's status information
        """
        return self._state["stages"].get(stage_name, {})

    def get_all_stages(self) -> Dict[str, Any]:
        """Get the status of all stages.

        Returns:
            Dictionary containing all stage status information
        """
        return self._state["stages"]

    def get_metrics(self) -> Dict[str, Any]:
        """Get the performance metrics for completed stages.

        Returns:
            Dictionary containing performance metrics
        """
        return self._state["metrics"]

    def record_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Record an event in the pipeline history.

        Args:
            event_type: Type of event (e.g., 'stage_start', 'stage_end', 'error')
            details: Dictionary containing event details
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "details": details
        }
        self._state["history"].append(event)

        # Keep history size manageable
        if len(self._state["history"]) > 1000:
            self._state["history"] = self._state["history"][-500:]

        self.save()

    def set_recovery_point(self, stage_name: str, progress: float = 0.0) -> None:
        """Set a recovery point for automatic recovery.

        Args:
            stage_name: Name of the stage to set as recovery point
            progress: Progress percentage at recovery point
        """
        self._state["recovery_point"] = {
            "stage": stage_name,
            "progress": progress,
            "timestamp": datetime.now().isoformat()
        }
        self.save()

    def get_recovery_point(self) -> Optional[Dict[str, Any]]:
        """Get the current recovery point.

        Returns:
            Dictionary containing recovery point information, or None if none exists
        """
        return self._state["recovery_point"]

    def clear_recovery_point(self) -> None:
        """Clear the current recovery point."""
        self._state["recovery_point"] = None
        self.save()