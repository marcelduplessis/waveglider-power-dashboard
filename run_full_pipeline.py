#!/usr/bin/env python3
"""
run_full_pipeline.py

Orchestrates the complete waveglider power analysis pipeline:
1. waveglider-data-wg1169.sh & waveglider-data-wg1170.sh (fetch new data from WGMS)
2. extract_amps_ports_full_wg1169.py & extract_amps_ports_full_wg1170.py (extract AMPS data)
3. power_analysis.py (generate interactive dashboards)
4. Deploy dashboard to remote server via rsync

Exit code:
  0 = all steps successful
  1 = data fetch failed
  2 = extract AMPS failed
  3 = power analysis failed
  
Note: Deployment failures do not cause pipeline failure (logged as warning).
"""

import sys
import subprocess
from pathlib import Path
import logging
from datetime import datetime

# Setup logging
log_dir = Path(__file__).parent / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f'pipeline_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent


def run_command(cmd, description, working_dir=None):
    """Run a command and log output."""
    logger.info(f"Starting: {description}")
    logger.info(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=working_dir or BASE_DIR,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.stdout:
            logger.info(f"Output:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Stderr:\n{result.stderr}")
        
        if result.returncode != 0:
            logger.error(f"Failed: {description} (exit code: {result.returncode})")
            return False
        
        logger.info(f"Completed: {description}")
        return True
    
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout: {description} exceeded 1 hour")
        return False
    except Exception as e:
        logger.error(f"Exception running {description}: {e}")
        return False


def main():
    """Run the full pipeline."""
    logger.info("=" * 80)
    logger.info("WAVEGLIDER POWER ANALYSIS PIPELINE START")
    logger.info(f"Base directory: {BASE_DIR}")
    logger.info("=" * 80)
    
    # Step 1: Fetch new data using shell scripts from waveglider-data-service
    data_service_dir = Path("/Users/xduplm/Google Drive/My Drive/projects/2026-whirls/platforms/wavegliders/waveglider-data-service")
    wg1169_shell_script = data_service_dir / 'waveglider-data-wg1169.sh'
    wg1170_shell_script = data_service_dir / 'waveglider-data-wg1170.sh'
    
    if not wg1169_shell_script.exists():
        logger.error(f"Required data fetch script not found: {wg1169_shell_script}")
        return 1
    
    if not wg1170_shell_script.exists():
        logger.error(f"Required data fetch script not found: {wg1170_shell_script}")
        return 1
    
    if not run_command(
        ['bash', str(wg1169_shell_script)],
        "waveglider-data-wg1169.sh",
        working_dir=str(data_service_dir)
    ):
        logger.error("Data fetch for WG1169 failed")
        return 1
    
    if not run_command(
        ['bash', str(wg1170_shell_script)],
        "waveglider-data-wg1170.sh",
        working_dir=str(data_service_dir)
    ):
        logger.error("Data fetch for WG1170 failed")
        return 1
    
    # Step 2: Extract AMPS data
    extract_wg1169 = BASE_DIR / 'extract_amps_ports_full_wg1169.py'
    extract_wg1170 = BASE_DIR / 'extract_amps_ports_full_wg1170.py'
    
    if not extract_wg1169.exists():
        logger.error(f"extract_amps_ports_full_wg1169.py not found at {extract_wg1169}")
        return 2
    
    if not extract_wg1170.exists():
        logger.error(f"extract_amps_ports_full_wg1170.py not found at {extract_wg1170}")
        return 2
    
    if not run_command(
        [sys.executable, str(extract_wg1169)],
        "extract_amps_ports_full_wg1169.py"
    ):
        return 2
    
    if not run_command(
        [sys.executable, str(extract_wg1170)],
        "extract_amps_ports_full_wg1170.py"
    ):
        return 2
    
    # Step 3: Run power analysis
    power_analysis_script = BASE_DIR / 'power_analysis.py'
    
    if not power_analysis_script.exists():
        logger.error(f"power_analysis.py not found at {power_analysis_script}")
        logger.info("Please run 'jupyter nbconvert --to script power_analysis.ipynb' to generate it")
        return 3
    
    if not run_command(
        [sys.executable, str(power_analysis_script)],
        "power_analysis.py"
    ):
        return 3
    
    # Step 4: Deploy dashboard to remote server
    deploy_file = BASE_DIR / 'exports' / 'wg_power_dashboard.html'
    if deploy_file.exists():
        if not run_command(
            [
                'rsync',
                str(deploy_file),
                'databot:/home/databot/share/www/html/'
            ],
            "Deploy dashboard to remote server"
        ):
            logger.warning("Dashboard deployment failed (but analysis completed successfully)")
            # Don't fail the pipeline on deployment error
    else:
        logger.warning(f"Dashboard file not found at {deploy_file} - skipping deployment")
    
    logger.info("=" * 80)
    logger.info("PIPELINE COMPLETE - All steps successful!")
    logger.info(f"Exports saved to: {BASE_DIR / 'exports'}")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 80)
    return 0


if __name__ == '__main__':
    sys.exit(main())
