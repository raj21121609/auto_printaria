import subprocess
import logging
import time

class Printer:
    def print_file(self, file_path, copies=1):
        """
        Send the file to the system's default printer.
        Supports multiple copies by printing sequentially.
        Returns True if all prints succeeded, False otherwise.
        """
        success = True
        for i in range(copies):
            try:
                # Use Windows 'print' command to send to default printer
                result = subprocess.run(['print', file_path], capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    logging.error(f"Print command failed for copy {i+1}: {result.stderr}")
                    success = False
                else:
                    logging.info(f"Successfully printed copy {i+1} of {file_path}")
                    # Small delay between prints to avoid overwhelming the printer
                    time.sleep(1)
            except subprocess.TimeoutExpired:
                logging.error(f"Print command timed out for copy {i+1}")
                success = False
            except Exception as e:
                logging.error(f"Error printing copy {i+1}: {e}")
                success = False
        return success