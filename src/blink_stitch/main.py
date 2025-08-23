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
from ..progress.state import PipelineState
from ..progress.ui import Dashboard
from ..progress.errors import ErrorManager
from pyannote.audio import Pipeline
from pyannote.core import Annotation
import yaml

from .helpers import discover_media_paths  # local import to avoid cycles

# Configure logging will be applied from config at runtime (see configure_logging())

def configure_logging(logging_cfg: dict) -> None:
    """Configure loguru logger from a config mapping.

    Supported keys in logging_cfg:
      - file: path to log file (default: 'blink_multicam.log')
      - level: logging level (e.g. 'INFO')
      - rotation: rotation string passed to loguru (e.g. '10 MB' or '1 week')
      - retention: retention policy for old logs (e.g. '7 days' or number of files)
      - compression: compression for rotated logs (e.g. 'zip')
    """
    # default values (match prior behaviour)
    log_file = logging_cfg.get("file", "blink_multicam.log")
    level = logging_cfg.get("level", "INFO")
    rotation = logging_cfg.get("rotation", "10 MB")
    retention = logging_cfg.get("retention", None)
    compression = logging_cfg.get("compression", None)

    # remove existing handlers to avoid duplicates in repeated runs
    try:
        logger.remove()  # remove all handlers
    except Exception:
        # best-effort fallback: ignore
        pass

    add_kwargs = {"rotation": rotation, "level": level}
    if retention is not None:
        add_kwargs["retention"] = retention
    if compression is not None:
        add_kwargs["compression"] = compression

    logger.add(log_file, **add_kwargs)

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
        # configure logging as early as possible from config
        logging_cfg = self.config.get("logging", {}) if isinstance(self.config, dict) else {}
        try:
            configure_logging(logging_cfg)
        except Exception as e:
            # fall back to a reasonable default if logging config fails
            logger.add("blink_multicam.log", rotation="10 MB", level="INFO")

        # cache dir used by extract/cluster helpers (optional)
        self.cache_dir = Path(self.config.get("cache_dir", ".cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.state = PipelineState(self.config["output_dir"])
        self.dashboard = Dashboard(self.state)
        self.error_manager = ErrorManager(self.state)
        self.pipeline = None

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from a YAML file.

        Args:
            config_path: Path to the configuration file

        Returns:
            Dictionary containing the configuration
        """
        try:
            with open(config_path, 'r') as f:
                cfg = yaml.safe_load(f)

            if not isinstance(cfg, dict):
                logger.error(f"Config file did not contain a mapping (expected dict): {config_path}")
                sys.exit(1)

            return cfg

        except FileNotFoundError:
            logger.error(f"Config file not found: {config_path}")
            sys.exit(1)
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in config file: {config_path}: {e}")
            sys.exit(1)

    def _initialize_pipeline(self) -> None:
        """Initialize the speaker diarization pipeline."""
        try:
            self.pipeline = Pipeline.from_pretrained(
                self.config["model_path"],
                use_auth_token=os.getenv("HF_TOKEN")
            )
            logger.info("Pipeline initialized successfully")
        except Exception as e:
            self.error_manager.report_error("fatal", str(e), "pipeline_initialization")
            raise

    def _load_audio_files(self) -> List[str]:
        """Load audio files from the specified directory (legacy behavior).

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

    def _discover_input_files(self) -> List[str]:
        """
        Discover input media files using the canonical helper.

        Precedence for discovery sources:
          1. self.config["input_paths"] if present (string or list)
          2. CLI-mapped values already merged into self.config before this call
          3. Legacy fallback to self.config["audio_dir"] (glob .wav/.flac) if nothing found

        Returns:
          Sorted list of discovered absolute file paths (strings).
        """
        paths = []

        # 1) explicit input_paths in config (string or list)
        ip = self.config.get("input_paths")
        if ip:
            if isinstance(ip, str):
                paths = [ip]
            else:
                try:
                    paths = list(ip)
                except Exception:
                    # best-effort coercion
                    paths = [str(p) for p in ip]

        # 2) if no input_paths present, CLI args should already have been merged into self.config
        # (so nothing extra to do here)

        # 3) if still empty, fallback to legacy audio_dir being treated as a single input path
        if not paths and self.config.get("audio_dir"):
            paths = [self.config["audio_dir"]]

        # Prepare recursive flag and optional extensions mapping
        recursive = self.config.get("recursive_discovery", True)
        exts = None
        # map optional config key "video_extensions" (may be comma-separated string or list)
        # Normalize extensions from config/CLI here so the helper receives a consistent list.
        # Accepted forms: "mp4", ".mp4", "MP4" or a list thereof. We convert to ".mp4" style lower-case.
        vexts = self.config.get("video_extensions")
        if vexts:
            raw = []
            if isinstance(vexts, str):
                raw = [e.strip() for e in vexts.split(",") if e.strip()]
            else:
                try:
                    raw = list(vexts)
                except Exception:
                    raw = []
            normed = []
            for e in raw:
                ee = e.lower()
                if not ee.startswith("."):
                    ee = "." + ee
                normed.append(ee)
            exts = normed if normed else None

        # Use the canonical helper for discovery. The helper implements the per-input non-recursive
        # fallback to immediate subdirectories (shallow, per-input behavior) so we avoid duplicating
        # that logic here. This keeps multi-root handling simple and unambiguous.
        discovered = discover_media_paths(paths, recursive=recursive, exts=exts)

        # If helper returned nothing and legacy audio_dir is present, preserve legacy glob fallback
        if not discovered and self.config.get("audio_dir"):
            audio_dir = Path(self.config["audio_dir"])
            if audio_dir.exists():
                audio_files = list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.flac"))
                discovered = [str(f.resolve()) for f in audio_files]

        # When non-recursive discovery returns mixed media, prefer audio files (.wav/.flac).
        # Rationale: for shallow scans users commonly want standalone audio captures (e.g. .wav/.flac)
        # rather than selecting among many small video files. This preference is applied only for
        # non-recursive discovery and only when top-level discovery yields any audio files, in order
        # to preserve the documented semantics for audio-first shallow scans.
        if not recursive and discovered:
            audio_only = [p for p in discovered if Path(p).suffix.lower() in {".wav", ".flac"}]
            if audio_only:
                discovered = audio_only
        discovered = sorted(discovered)

        # Logging: number discovered and sample first/last
        if discovered:
            logger.info(
                "Discovered %d media files. first=%s last=%s",
                len(discovered),
                discovered[0],
                discovered[-1],
            )
        else:
            logger.info("Discovered 0 media files")

        return discovered

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
