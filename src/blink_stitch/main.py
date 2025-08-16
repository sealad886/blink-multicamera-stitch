"""Main application for the blink-multicamera-stitch project.

This script orchestrates the pipeline for processing multiple camera inputs,
stitching them together, and generating the final output.
"""

from .helpers import set_openmp_env
set_openmp_env()

import os
import sys
import json
from typing import Dict, List
from pathlib import Path
import argparse
from loguru import logger
from progress.state import PipelineState
from progress.ui import Dashboard
from progress.errors import ErrorManager
from pyannote.audio import Pipeline
from pyannote.core import Annotation

# Configure logging
logger.add("blink_multicam.log", rotation="10 MB", level="INFO")

# Constants
DEFAULT_CONFIG_PATH = "config.json"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_AUDIO_DIR = "audio_samples"
DEFAULT_MODEL_PATH = "pyannote/speaker-diarization-3.1"
DEFAULT_PROTOCOL = "AMI.MixHeadset"

class BlinkMulticameraStitch:
    """Main class for the blink-multicamera-stitch application."""

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        """Initialize the application with configuration.

        Args:
            config_path: Path to the configuration file
        """
        self.config = self._load_config(config_path)
        self.state = PipelineState(self.config["output_dir"])
        self.dashboard = Dashboard(self.state)
        self.error_manager = ErrorManager(self.state)
        self.pipeline = None

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from file.

        Args:
            config_path: Path to the configuration file

        Returns:
            Dictionary containing the configuration
        """
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {config_path}")
            sys.exit(1)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in config file: {config_path}")
            sys.exit(1)

    def _initialize_pipeline(self) -> None:
        """Initialize the speaker diarization pipeline."""
        try:
            self.pipeline = Pipeline.from_pretrained(
                self.config["model_path"],
                use_auth_token=os.getenv("HUGGINGFACE_TOKEN")
            )
            logger.info("Pipeline initialized successfully")
        except Exception as e:
            self.error_manager.report_error("fatal", str(e), "pipeline_initialization")
            raise

    def _load_audio_files(self) -> List[str]:
        """Load audio files from the specified directory.

        Returns:
            List of paths to audio files
        """
        audio_dir = Path(self.config["audio_dir"])
        if not audio_dir.exists():
            logger.error(f"Audio directory not found: {audio_dir}")
            return []

        audio_files = list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.flac"))
        logger.info(f"Found {len(audio_files)} audio files")
        return [str(f) for f in audio_files]

    def _process_audio(self, audio_files: List[str]) -> Dict[str, Annotation]:
        """Process audio files using the pipeline.

        Args:
            audio_files: List of paths to audio files

        Returns:
            Dictionary mapping file paths to their annotations
        """
        if not self.pipeline:
            raise RuntimeError("Pipeline not initialized")

        results = {}

        for audio_file in audio_files:
            try:
                # Update stage status
                self.dashboard.update_stage("processing", "running", 0.0)

                # Process the audio file
                annotation = self.pipeline(audio_file)

                # Update progress
                progress = (audio_files.index(audio_file) + 1) / len(audio_files)
                self.dashboard.update_stage("processing", "running", progress)

                results[audio_file] = annotation

            except Exception as e:
                self.error_manager.report_error("fatal", str(e), "audio_processing")
                self.dashboard.add_error("fatal", str(e), "processing")
                continue

        return results

    def _generate_output(self, annotations: Dict[str, Annotation]) -> None:
        """Generate output from processed annotations.

        Args:
            annotations: Dictionary of file paths to annotations
        """
        try:
            # Update stage status
            self.dashboard.update_stage("generating", "running", 0.0)

            output_dir = Path(self.config["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)

            # Process each annotation
            for i, (audio_file, annotation) in enumerate(annotations.items()):
                # Create output file path
                file_name = Path(audio_file).stem
                output_file = output_dir / f"{file_name}_output.json"

                # Save annotation to JSON
                with open(output_file, 'w') as f:
                    # Convert annotation to dict using supported method
                    annotation_dict = {
                        "segments": [
                            {
                                "start": segment.start,
                                "end": segment.end,
                                "segment": segment,
                                "track": track,
                                "label": label
                            }
                            for segment, track, label in annotation.itertracks(yield_label=True) # pyright: ignore[reportAssignmentType]
                        ]
                    }
                    json.dump(annotation_dict, f, indent=2)

                # Update progress
                progress = (i + 1) / len(annotations)
                self.dashboard.update_stage("generating", "running", progress)

            # Mark stage as completed
            self.dashboard.update_stage("generating", "completed", 1.0)

            logger.info(f"Output generated in {output_dir}")

        except Exception as e:
            self.error_manager.report_error("fatal", str(e), "output_generation")
            self.dashboard.add_error("fatal", str(e), "generating")
            raise

    def run(self) -> None:
        """Run the main pipeline."""
        try:
            # Initialize the dashboard
            with self.dashboard:
                # Add stages to the dashboard
                self.dashboard.add_stage("initialization")
                self.dashboard.add_stage("processing")
                self.dashboard.add_stage("generating")

                # Run initialization stage
                self.dashboard.update_stage("initialization", "running", 0.0)
                self._initialize_pipeline()
                self.dashboard.update_stage("initialization", "completed", 1.0)

                # Run processing stage
                audio_files = self._load_audio_files()
                if not audio_files:
                    self.dashboard.add_error("fatal", "No audio files found", "processing")
                    return

                annotations = self._process_audio(audio_files)

                # Run generating stage
                self._generate_output(annotations)

                # Mark all stages as completed
                self.dashboard.update_stage("processing", "completed", 1.0)

                logger.info("Pipeline completed successfully")

        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            self.dashboard.add_error("fatal", str(e), "pipeline")
            sys.exit(1)

def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(description="blink-multicamera-stitch application")
    parser.add_argument("--config", help="Path to configuration file", default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()

    app = BlinkMulticameraStitch(args.config)
    app.run()

if __name__ == "__main__":
    main()
