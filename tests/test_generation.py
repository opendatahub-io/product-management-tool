#!/usr/bin/env python3
"""
Basic end-to-end regression tests for product onboarding script.

Tests that KRD and pipelinerun generation produces consistent output
for both full-container and disk-image pipeline types.
"""

import os
import shutil
import tempfile
import filecmp
from pathlib import Path
import pytest

# Import the functions we want to test
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from onboard-product.py (need to use importlib for dash in filename)
import importlib.util
spec = importlib.util.spec_from_file_location("onboard_product", 
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "onboard-product.py"))
onboard_product = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboard_product)

# Import the functions we need
load_config_and_data = onboard_product.load_config_and_data
render_krd_templates = onboard_product.render_krd_templates
render_pipelinerun_templates = onboard_product.render_pipelinerun_templates


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
        
        for root, dirs, files in os.walk(expected_dir):
            for file in files:
                if file not in ignore_files:
                    rel_path = Path(root).relative_to(expected_dir) / file
                    expected_files.add(rel_path)
        
        for root, dirs, files in os.walk(actual_dir):
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
                    with open(expected_file, 'r') as f:
                        expected_content = f.read()[:500]
                    with open(actual_file, 'r') as f:
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
        
        # Load config and generate KRD resources
        config, data = load_config_and_data(str(config_file))
        
        # Override paths to use temp directory
        render_krd_templates(
            data, 
            config["krd_template_dir"], 
            str(self.temp_krd), 
            config["cluster"]
        )
        
        # Compare generated output with expected
        differences = self.compare_directories(expected_dir, self.temp_krd)
        
        if differences:
            pytest.fail(f"KRD generation differences for {pipeline_type}:\\n" + 
                       "\\n".join(differences))
    
    @pytest.mark.parametrize("pipeline_type", ["full-container", "disk-image"])
    def test_pipelinerun_generation(self, pipeline_type):
        """Test pipelinerun generation for both pipeline types."""
        config_file = self.test_dir / f"configs/test-{pipeline_type}.yaml"
        expected_dir = self.test_dir / f"expected/{pipeline_type}/pipelinerun"
        
        # Load config and generate pipelinerun resources  
        config, data = load_config_and_data(str(config_file))
        
        # Override paths to use temp directory
        render_pipelinerun_templates(
            data,
            config["pipelinerun_template_dir"],
            str(self.temp_pipelinerun)
        )
        
        # Compare generated output with expected
        differences = self.compare_directories(expected_dir, self.temp_pipelinerun)
        
        if differences:
            pytest.fail(f"Pipelinerun generation differences for {pipeline_type}:\\n" + 
                       "\\n".join(differences))
    
    @pytest.mark.parametrize("pipeline_type", ["full-container", "disk-image"])
    def test_end_to_end_generation(self, pipeline_type):
        """Test complete end-to-end generation (both KRD and pipelinerun)."""
        config_file = self.test_dir / f"configs/test-{pipeline_type}.yaml"
        expected_krd_dir = self.test_dir / f"expected/{pipeline_type}/krd"
        expected_pipelinerun_dir = self.test_dir / f"expected/{pipeline_type}/pipelinerun"
        
        # Load config
        config, data = load_config_and_data(str(config_file))
        
        # Generate both KRD and pipelinerun resources
        render_krd_templates(
            data, 
            config["krd_template_dir"], 
            str(self.temp_krd), 
            config["cluster"]
        )
        
        render_pipelinerun_templates(
            data,
            config["pipelinerun_template_dir"],
            str(self.temp_pipelinerun)
        )
        
        # Compare both outputs
        krd_differences = self.compare_directories(expected_krd_dir, self.temp_krd)
        pipelinerun_differences = self.compare_directories(expected_pipelinerun_dir, self.temp_pipelinerun)
        
        all_differences = []
        if krd_differences:
            all_differences.extend([f"KRD: {diff}" for diff in krd_differences])
        if pipelinerun_differences:
            all_differences.extend([f"Pipelinerun: {diff}" for diff in pipelinerun_differences])
            
        if all_differences:
            pytest.fail(f"End-to-end generation differences for {pipeline_type}:\\n" + 
                       "\\n".join(all_differences))


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__])