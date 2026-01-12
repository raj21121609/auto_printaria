"""
Printer Module for Print Worker

Handles printing on Windows using multiple methods:
1. SumatraPDF (recommended for PDFs) - if available
2. win32print API - for raw printing
3. ShellExecute "print" verb - fallback

Supports:
- PDF documents
- Images (JPG, PNG)
- Word documents (via default application)
"""

import subprocess
import os
import logging
import time
import shutil
from typing import List, Optional

logger = logging.getLogger(__name__)


class Printer:
    """
    Windows printer interface.
    
    Uses the most reliable method available for each file type.
    """
    
    def __init__(self, printer_name: str = None):
        """
        Initialize printer.
        
        Args:
            printer_name: Specific printer to use (None = system default)
        """
        self.printer_name = printer_name or ""
        self.sumatra_path = self._find_sumatra()
        
        if self.sumatra_path:
            logger.info(f"SumatraPDF found: {self.sumatra_path}")
        else:
            logger.info("SumatraPDF not found - will use fallback methods")
    
    def _find_sumatra(self) -> Optional[str]:
        """
        Find SumatraPDF installation.
        
        SumatraPDF is the recommended tool for silent PDF printing on Windows.
        """
        # Common installation paths
        paths = [
            r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
            r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
            os.path.expanduser(r"~\AppData\Local\SumatraPDF\SumatraPDF.exe"),
            # Portable version in worker directory
            os.path.join(os.path.dirname(__file__), "SumatraPDF.exe"),
        ]
        
        for path in paths:
            if os.path.isfile(path):
                return path
        
        # Try PATH
        sumatra_in_path = shutil.which("SumatraPDF")
        if sumatra_in_path:
            return sumatra_in_path
        
        return None
    
    def get_available_printers(self) -> List[str]:
        """
        Get list of available printers.
        
        Returns:
            List of printer names
        """
        printers = []
        
        try:
            # Try win32print if available
            import win32print
            printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
            
        except ImportError:
            # Fallback: use wmic command
            try:
                result = subprocess.run(
                    ['wmic', 'printer', 'get', 'name'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    printers = [line.strip() for line in lines[1:] if line.strip()]
                    
            except Exception as e:
                logger.warning(f"Could not enumerate printers: {e}")
        
        return printers
    
    def get_default_printer(self) -> Optional[str]:
        """Get the system default printer name."""
        try:
            import win32print
            return win32print.GetDefaultPrinter()
        except ImportError:
            try:
                result = subprocess.run(
                    ['wmic', 'printer', 'where', 'default=true', 'get', 'name'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        return lines[1].strip()
            except Exception:
                pass
        return None
    
    def print_file(
        self,
        file_path: str,
        copies: int = 1,
        print_type: str = "BW"
    ) -> bool:
        """
        Print a file.
        
        Args:
            file_path: Path to file to print
            copies: Number of copies
            print_type: Print type (BW, COLOR, BOTH)
            
        Returns:
            True if printing succeeded, False otherwise
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False
        
        ext = os.path.splitext(file_path)[1].lower()
        logger.info(f"Printing: {file_path} ({copies} copies, {print_type})")
        
        # For BOTH print type, we print twice (once in each mode if printer supports)
        # For simplicity, we treat it as printing the document twice
        total_copies = copies
        if print_type == "BOTH":
            total_copies = copies * 2  # One set BW, one set color
            logger.info(f"BOTH mode: printing {total_copies} copies total")
        
        # Choose printing method based on file type
        if ext == '.pdf':
            return self._print_pdf(file_path, total_copies)
        elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            return self._print_image(file_path, total_copies)
        elif ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
            return self._print_office(file_path, total_copies)
        else:
            return self._print_generic(file_path, total_copies)
    
    def _print_pdf(self, file_path: str, copies: int) -> bool:
        """
        Print a PDF file.
        
        Uses SumatraPDF if available (recommended), otherwise falls back.
        """
        if self.sumatra_path:
            return self._print_with_sumatra(file_path, copies)
        else:
            return self._print_generic(file_path, copies)
    
    def _print_with_sumatra(self, file_path: str, copies: int) -> bool:
        """
        Print using SumatraPDF.
        
        SumatraPDF command line:
        SumatraPDF.exe -print-to "Printer Name" -print-settings "copies" file.pdf
        
        -print-to-default uses default printer
        -silent suppresses UI
        """
        try:
            for i in range(copies):
                cmd = [self.sumatra_path]
                
                if self.printer_name:
                    cmd.extend(['-print-to', self.printer_name])
                else:
                    cmd.append('-print-to-default')
                
                cmd.extend([
                    '-silent',
                    '-print-settings', 'fit',  # Fit to page
                    file_path
                ])
                
                logger.debug(f"Running: {' '.join(cmd)}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode != 0:
                    logger.error(f"SumatraPDF failed: {result.stderr}")
                    return False
                
                logger.info(f"Printed copy {i + 1}/{copies}")
                
                # Brief delay between copies
                if i < copies - 1:
                    time.sleep(1)
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Print command timed out")
            return False
            
        except Exception as e:
            logger.error(f"SumatraPDF error: {e}")
            return False
    
    def _print_image(self, file_path: str, copies: int) -> bool:
        """
        Print an image file.
        
        Uses Windows Photo Viewer or default image handler.
        """
        return self._print_generic(file_path, copies)
    
    def _print_office(self, file_path: str, copies: int) -> bool:
        """
        Print Office documents.
        
        Uses the default application's print functionality.
        """
        return self._print_generic(file_path, copies)
    
    def _print_generic(self, file_path: str, copies: int) -> bool:
        """
        Generic print using Windows ShellExecute "print" verb.
        
        This opens the file with its associated application and prints.
        """
        try:
            for i in range(copies):
                # Use os.startfile with "print" operation
                # This is equivalent to right-click -> Print
                os.startfile(file_path, "print")
                
                logger.info(f"Sent copy {i + 1}/{copies} to print queue")
                
                # Wait for print job to be queued
                time.sleep(3)
            
            return True
            
        except OSError as e:
            logger.error(f"Failed to print {file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Print error: {e}")
            return False
    
    def _print_with_win32(self, file_path: str, copies: int) -> bool:
        """
        Print using win32print API.
        
        More control but requires pywin32 package.
        Primarily useful for raw text/PCL printing.
        """
        try:
            import win32print
            import win32api
            
            printer_name = self.printer_name or win32print.GetDefaultPrinter()
            
            for i in range(copies):
                # ShellExecute print
                win32api.ShellExecute(
                    0,
                    "print",
                    file_path,
                    f'/d:"{printer_name}"' if printer_name else None,
                    ".",
                    0  # SW_HIDE
                )
                
                logger.info(f"Printed copy {i + 1}/{copies}")
                time.sleep(2)
            
            return True
            
        except ImportError:
            logger.warning("pywin32 not available")
            return False
        except Exception as e:
            logger.error(f"win32print error: {e}")
            return False
