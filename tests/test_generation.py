#!/usr/bin/env python3
"""
Basic end-to-end regression tests for product onboarding script.

Tests that KRD and pipelinerun generation produces consistent output
for both full-container and disk-image pipeline types.
"""

import filecmp
import os
import shutil

# Import the functions we want to test
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from config.py and onboard-product.py
# Import from onboard-product.py (need to use importlib for dash in filename)
import importlib.util

from ruamel.yaml import YAML

from config import Config

spec = importlib.util.spec_from_file_location(
    "onboard_product",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "onboard-product.py"),
)
onboard_product = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboard_product)

# Import the functions we need
render_krd_templates = onboard_product.render_krd_templates
render_pipelinerun_templates = onboard_product.render_pipelinerun_templates

# Initialize YAML parser
yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.explicit_start = True
yaml.width = 4096


class TestGeneration:
    """Test generation of KRD and pipelinerun resources."""

    def setup_method(self):
        """Set up test environment with temporary directories."""
        self.test_dir = Path(__file__).parent
        self.temp_dir = Path(tempfile.mkdtemp())
        self.temp_krd = self.temp_dir / "krd"
        self.temp_pipelinerun = self.temp_dir / "pipelinerun"
        self.temp_krd.mkdir()
        self.temp_pipelinerun.mkdir()

    def teardown_method(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.temp_dir)

    def compare_directories(self, expected_dir, actual_dir, ignore_files=None):
        """
        Recursively compare two directory trees.

        Args:
            expected_dir (Path): Expected output directory
            actual_dir (Path): Actual generated directory
            ignore_files (set): Files to ignore during comparison

        Returns:
            list: List of differences found
        """
        if ignore_files is None:
            ignore_files = set()

        differences = []

        if not actual_dir.exists():
            differences.append(f"Missing directory: {actual_dir}")
            return differences

        # Compare directory structure
        expected_files = set()
        actual_files = set()

        for root, _dirs, files in os.walk(expected_dir):
            for file in files:
                if file not in ignore_files:
                    rel_path = Path(root).relative_to(expected_dir) / file
                    expected_files.add(rel_path)

        for root, _dirs, files in os.walk(actual_dir):
            for file in files:
                if file not in ignore_files:
                    rel_path = Path(root).relative_to(actual_dir) / file
                    actual_files.add(rel_path)

        # Check for missing files
        missing_files = expected_files - actual_files
        for missing in missing_files:
            differences.append(f"Missing file: {missing}")

        # Check for extra files
        extra_files = actual_files - expected_files
        for extra in extra_files:
            differences.append(f"Extra file: {extra}")

        # Compare file contents
        for file_path in expected_files.intersection(actual_files):
            expected_file = expected_dir / file_path
            actual_file = actual_dir / file_path

            if not filecmp.cmp(expected_file, actual_file, shallow=False):
                differences.append(f"Content differs: {file_path}")

                # Show first few lines of difference for debugging
                try:
                    with open(expected_file) as f:
                        expected_content = f.read()[:500]
                    with open(actual_file) as f:
                        actual_content = f.read()[:500]
                    differences.append(f"  Expected preview: {expected_content}")
                    differences.append(f"  Actual preview: {actual_content}")
                except Exception:
                    # If files are binary or can't be read, just note the difference
                    pass

        return differences

    @pytest.mark.parametrize("pipeline_type", ["full-container", "disk-image"])
    def test_krd_generation(self, pipeline_type):
        """Test KRD resource generation for both pipeline types."""
        config_file = self.test_dir / f"configs/test-{pipeline_type}.yaml"
        expected_dir = self.test_dir / f"expected/{pipeline_type}/krd"

        # Load configuration using new Config system
        config = Config()

        # Load product data from YAML
        with open(config_file) as f:
            data = yaml.load(f)

        # Generate KRD resources (using temp directory for output)
        render_krd_templates(
            data,
            str(config["krd_template_dir"]),
            str(self.temp_krd),
            config["cluster"],
            recreate=False,
        )

        # Compare generated output with expected
        differences = self.compare_directories(expected_dir, self.temp_krd)

        if differences:
            pytest.fail(
                f"KRD generation differences for {pipeline_type}:\\n" + "\\n".join(differences)
            )

    @pytest.mark.parametrize("pipeline_type", ["full-container", "disk-image"])
    def test_pipelinerun_generation(self, pipeline_type):
        """Test pipelinerun generation for both pipeline types."""
        config_file = self.test_dir / f"configs/test-{pipeline_type}.yaml"
        expected_dir = self.test_dir / f"expected/{pipeline_type}/pipelinerun"

        # Load configuration using new Config system
        config = Config()

        # Load product data from YAML
        with open(config_file) as f:
            data = yaml.load(f)

        # Generate pipelinerun resources (using temp directory for output)
        render_pipelinerun_templates(
            data, str(config["pipelinerun_template_dir"]), str(self.temp_pipelinerun)
        )

        # Compare generated output with expected
        differences = self.compare_directories(expected_dir, self.temp_pipelinerun)

        if differences:
            pytest.fail(
                f"Pipelinerun generation differences for {pipeline_type}:\\n"
                + "\\n".join(differences)
            )

    @pytest.mark.parametrize("pipeline_type", ["full-container", "disk-image"])
    def test_end_to_end_generation(self, pipeline_type):
        """Test complete end-to-end generation (both KRD and pipelinerun)."""
        config_file = self.test_dir / f"configs/test-{pipeline_type}.yaml"
        expected_krd_dir = self.test_dir / f"expected/{pipeline_type}/krd"
        expected_pipelinerun_dir = self.test_dir / f"expected/{pipeline_type}/pipelinerun"

        # Load configuration using new Config system
        config = Config()

        # Load product data from YAML
        with open(config_file) as f:
            data = yaml.load(f)

        # Generate both KRD and pipelinerun resources
        render_krd_templates(
            data,
            str(config["krd_template_dir"]),
            str(self.temp_krd),
            config["cluster"],
            recreate=False,
        )

        render_pipelinerun_templates(
            data, str(config["pipelinerun_template_dir"]), str(self.temp_pipelinerun)
        )

        # Compare both outputs
        krd_differences = self.compare_directories(expected_krd_dir, self.temp_krd)
        pipelinerun_differences = self.compare_directories(
            expected_pipelinerun_dir, self.temp_pipelinerun
        )

        all_differences = []
        if krd_differences:
            all_differences.extend([f"KRD: {diff}" for diff in krd_differences])
        if pipelinerun_differences:
            all_differences.extend([f"Pipelinerun: {diff}" for diff in pipelinerun_differences])

        if all_differences:
            pytest.fail(
                f"End-to-end generation differences for {pipeline_type}:\\n"
                + "\\n".join(all_differences)
            )


class TestMultiConfig:
    """Test multi-config processing with glob patterns and --config-dir."""

    def setup_method(self):
        """Set up test environment with temporary directories."""
        self.test_dir = Path(__file__).parent
        self.temp_dir = Path(tempfile.mkdtemp())
        self.temp_krd = self.temp_dir / "krd"
        self.temp_krd.mkdir()

    def teardown_method(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.temp_dir)

    def test_collect_config_files_glob_pattern(self):
        """Test collecting config files using glob pattern."""
        from pathlib import Path

        # Import collect_config_files from onboard-product.py
        config_files = onboard_product.collect_config_files(["tests/configs/test-*.yaml"], None)

        # Should find both test-full-container.yaml and test-disk-image.yaml
        assert len(config_files) == 2
        assert all(isinstance(cf, Path) for cf in config_files)
        assert any("test-full-container.yaml" in str(cf) for cf in config_files)
        assert any("test-disk-image.yaml" in str(cf) for cf in config_files)

    def test_collect_config_files_config_dir(self):
        """Test collecting config files using --config-dir."""
        from pathlib import Path

        config_dir = self.test_dir / "configs/multi-config-test"
        config_files = onboard_product.collect_config_files(None, config_dir)

        # Should find all 3 config files in multi-config-test directory
        assert len(config_files) == 3
        assert all(isinstance(cf, Path) for cf in config_files)
        assert all(cf.suffix == ".yaml" for cf in config_files)

    def test_collect_config_files_combined(self):
        """Test combining --config glob pattern and --config-dir."""
        from pathlib import Path

        config_dir = self.test_dir / "configs/multi-config-test"
        config_files = onboard_product.collect_config_files(
            ["tests/configs/test-full-container.yaml"], config_dir
        )

        # Should find test-full-container.yaml + all 3 from multi-config-test
        assert len(config_files) == 4
        assert all(isinstance(cf, Path) for cf in config_files)

    def test_collect_config_files_no_duplicates(self):
        """Test that duplicate paths are removed."""

        config_dir = self.test_dir / "configs/multi-config-test"
        # Specify a file both as --config and it's in --config-dir
        config_files = onboard_product.collect_config_files(
            ["tests/configs/multi-config-test/config1.yaml"], config_dir
        )

        # Should only appear once
        assert len(config_files) == 3  # config1, config2, config3 (no duplicates)

    def test_collect_config_files_error_no_configs(self):
        """Test error when no configs are found."""
        with pytest.raises(ValueError, match="No config files found"):
            onboard_product.collect_config_files(["nonexistent/*.yaml"], None)

    def test_collect_config_files_error_bad_directory(self):
        """Test error when directory doesn't exist."""
        from pathlib import Path

        bad_dir = Path("/nonexistent/directory")
        with pytest.raises(ValueError, match="Config directory does not exist"):
            onboard_product.collect_config_files(None, bad_dir)

    def test_multi_config_krd_generation(self):
        """Test KRD generation with multiple configs."""
        config_dir = self.test_dir / "configs/multi-config-test"
        config = Config()

        # Collect configs using our helper function
        config_files = onboard_product.collect_config_files(None, config_dir)

        # Load and merge all definitions
        all_definitions = []
        for config_file in config_files:
            with open(config_file) as f:
                data = yaml.load(f)
                all_definitions.extend(data.get("definitions", []))

        merged_data = {"definitions": all_definitions}

        # Generate KRD resources
        render_krd_templates(
            merged_data,
            str(config["krd_template_dir"]),
            str(self.temp_krd),
            config["cluster"],
            recreate=False,
        )

        # Verify all 3 applications were processed
        tenants_dir = self.temp_krd / "tenants-config/cluster/stone-prod-p02/tenants"

        # Check multi-test-tenant (2 apps: app1 and app2)
        multi_test_tenant = tenants_dir / "multi-test-tenant"
        assert multi_test_tenant.exists()
        assert (multi_test_tenant / "multi-test-app1/main").exists()
        assert (multi_test_tenant / "multi-test-app2/main").exists()

        # Check another-tenant (1 app: app3)
        another_tenant = tenants_dir / "another-tenant"
        assert another_tenant.exists()
        assert (another_tenant / "multi-test-app3/v1-0").exists()


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__])
