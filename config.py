"""
Configuration management for product onboarding tool.

Provides a flexible configuration system with the following priority order:
1. CLI arguments (highest priority)
2. Environment variables (backward compatible)
3. Configuration file (.onboard-config.toml)
4. Sensible defaults (lowest priority)

This ensures backward compatibility with existing environment variable usage
while providing modern, flexible configuration options.
"""

import os
import tomllib
from pathlib import Path
from typing import Any


class Config:
    """
    Configuration management with hierarchical loading.

    Configuration is loaded in priority order:
    CLI arguments > Environment variables > Config file > Defaults

    Environment Variables (backward compatible):
        TEMPLATES_DIR: KRD templates directory
        KRD_PATH: Output path for KRD resources
        CLUSTER: Target Kubernetes cluster name
        PIPELINERUN_TEMPLATE_DIR: Pipelinerun templates directory
        GITLAB_REPO_PATH: Base path for GitLab repository checkouts

    Config File Format (.onboard-config.toml):
        [paths]
        krd_path = "./output/krd"
        gitlab_repo_path = "./output/pipelinerun"
        templates_dir = "./templates/KRD"
        pipelinerun_template_dir = "./templates/pipelinerun"

        [cluster]
        name = "stone-prod-p02"
    """

    DEFAULT_CONFIG_FILE = ".onboard-config.toml"

    # Sensible defaults: relative to current working directory, not hardcoded user paths
    DEFAULTS = {
        "krd_template_dir": Path("templates/KRD"),
        "krd_path": Path("output/krd"),
        "gitlab_repo_path": Path("output/pipelinerun"),
        "pipelinerun_template_dir": Path("templates/pipelinerun"),
        "cluster": "stone-prod-p02",
        "repo_overrides": {},
    }

    def __init__(
        self,
        config_file: Path | None = None,
        cli_overrides: dict[str, Any] | None = None,
    ):
        """
        Initialize configuration with hierarchical loading.

        Args:
            config_file: Path to TOML configuration file (default: ./.onboard-config.toml)
            cli_overrides: Dictionary of CLI argument overrides
        """
        self.config = self._load_config(config_file, cli_overrides or {})

    def _load_config(
        self, config_file: Path | None, cli_overrides: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Load configuration in priority order: defaults < config file < env < CLI.

        Args:
            config_file: Path to TOML configuration file
            cli_overrides: CLI argument overrides

        Returns:
            Merged configuration dictionary
        """
        config = self.DEFAULTS.copy()

        # 1. Load from config file (if exists)
        config.update(self._load_from_file(config_file))

        # 2. Override with environment variables (backward compatible)
        config.update(self._load_from_env())

        # 3. Override with CLI arguments (highest priority)
        config.update({k: v for k, v in cli_overrides.items() if v is not None})

        # Convert all paths to resolved Path objects
        return self._resolve_paths(config)

    def _load_from_file(self, config_file: Path | None) -> dict[str, Any]:
        """
        Load configuration from TOML file.

        Args:
            config_file: Path to TOML file, or None to use default

        Returns:
            Dictionary of configuration values from file
        """
        if config_file is None:
            config_file = Path.cwd() / self.DEFAULT_CONFIG_FILE

        if not config_file.exists():
            return {}

        try:
            with open(config_file, "rb") as f:
                data = tomllib.load(f)

            # Flatten nested TOML structure to match our config keys
            result = {
                "krd_template_dir": data.get("paths", {}).get("templates_dir"),
                "krd_path": data.get("paths", {}).get("krd_path"),
                "gitlab_repo_path": data.get("paths", {}).get("gitlab_repo_path"),
                "pipelinerun_template_dir": data.get("paths", {}).get("pipelinerun_template_dir"),
                "cluster": data.get("cluster", {}).get("name"),
            }
            if "repo_overrides" in data:
                result["repo_overrides"] = {
                    k: str(Path(v).expanduser().resolve())
                    for k, v in data["repo_overrides"].items()
                }
            return result
        except (tomllib.TOMLDecodeError, OSError) as e:
            print(f"Warning: Failed to load config file {config_file}: {e}")
            return {}

    def _load_from_env(self) -> dict[str, Any]:
        """
        Load configuration from environment variables.

        Maintains backward compatibility with existing environment variable usage.

        Returns:
            Dictionary of configuration values from environment
        """
        env_config = {}

        if krd_template_dir := os.environ.get("TEMPLATES_DIR"):
            env_config["krd_template_dir"] = krd_template_dir

        if krd_path := os.environ.get("KRD_PATH"):
            env_config["krd_path"] = krd_path

        if gitlab_repo_path := os.environ.get("GITLAB_REPO_PATH"):
            env_config["gitlab_repo_path"] = gitlab_repo_path

        if pipelinerun_template_dir := os.environ.get("PIPELINERUN_TEMPLATE_DIR"):
            env_config["pipelinerun_template_dir"] = pipelinerun_template_dir

        if cluster := os.environ.get("CLUSTER"):
            env_config["cluster"] = cluster

        return env_config

    def _resolve_paths(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Convert string paths to resolved Path objects.

        All paths are expanded (~/ becomes home directory) and resolved to
        absolute paths for consistency.

        Args:
            config: Configuration dictionary with potential string paths

        Returns:
            Configuration dictionary with Path objects
        """
        path_keys = [
            "krd_template_dir",
            "krd_path",
            "gitlab_repo_path",
            "pipelinerun_template_dir",
        ]
        # repo_overrides is a dict, not a path — skip it in path resolution

        resolved_config = config.copy()
        for key in path_keys:
            if resolved_config[key] is not None:
                path_value = resolved_config[key]
                # Convert to Path if it's a string
                if isinstance(path_value, str):
                    path_value = Path(path_value)
                # Expand ~ and resolve to absolute path
                resolved_config[key] = path_value.expanduser().resolve()

        return resolved_config

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return self.config.get(key, default)

    def __getitem__(self, key: str) -> Any:
        """
        Dict-like access to configuration values.

        Args:
            key: Configuration key

        Returns:
            Configuration value

        Raises:
            KeyError: If key not found in configuration
        """
        return self.config[key]

    def __repr__(self) -> str:
        """String representation showing all configuration values."""
        return f"Config({self.config})"
