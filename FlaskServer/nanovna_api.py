#!/usr/bin/env python3
"""
nanovna_api.py

This module provides a Python interface to communicate with a NanoVNA device
over USB/serial. It is adapted from the original NanoVNA script to support
integration with a Flask web server or other Python applications.

Future improvements:
- Flask endpoints can import NanoVNA class to run scans,
  retrieve data, generate plots, etc.
- Additional functions for error handling, logging, and concurrency.
"""

import time
import serial
import numpy as np
from serial.tools import list_ports

# Constants for NanoVNA's USB vendor and product IDs
VID = 0x0483  # 1155 decimal
PID = 0x5740  # 22336 decimal

# Reference level used for reflection/gamma calculations
REF_LEVEL = (1 << 9)

def get_nano_port() -> str:
    """
    Automatically finds the first NanoVNA device based on Vendor ID (VID)
    and Product ID (PID). Raises OSError if not found.
    """
    device_list = list_ports.comports()
    for device in device_list:
        if device.vid == VID and device.pid == PID:
            return device.device
    raise OSError("NanoVNA device not found on any serial port.")

class NanoVNA:
    """
    A class that interfaces with a NanoVNA device over serial/USB.
    Capabilities:
      - Setting frequencies and sweep ranges
      - Fetching raw data for further processing (TDR, S11, etc.)
      - Generating data arrays to be plotted (magnitude, phase, VSWR, etc.)
      - (Optional) CLI usage if desired
    """

    def __init__(self, dev: str = None):
        """
        :param dev: The serial device path (e.g., /dev/ttyACM0 on Linux, COM3 on Windows).
                    If None, attempts to auto-detect based on VID/PID.
        """
        self.dev = dev or get_nano_port()
        self.serial = None
        self._frequencies = None
        self.points = 101

    @property
    def frequencies(self) -> np.ndarray:
        """
        Returns the cached frequency array if available. Use set_frequencies() or
        fetch_frequencies() to update.
        """
        return self._frequencies

    def set_frequencies(self, start: float = 1e6, stop: float = 900e6, points: int = None):
        """
        Pre-calculates a frequency array (linearly spaced). Actual device
        sweep commands are sent separately with set_sweep() or send_scan().
        """
        if points:
            self.points = points
        self._frequencies = np.linspace(start, stop, self.points)

    def open(self):
        """Opens the serial connection to the NanoVNA, if not already opened."""
        if self.serial is None:
            self.serial = serial.Serial(self.dev)

    def close(self):
        """Closes the serial connection, if open."""
        if self.serial:
            self.serial.close()
        self.serial = None

    def send_command(self, cmd: str):
        """
        Sends a plain-text command to the NanoVNA and discards the first
        empty line in response.
        """
        self.open()
        self.serial.write(cmd.encode())
        self.serial.readline()  # discard empty line

    def set_sweep(self, start: float = None, stop: float = None):
        """Configure the device's sweep range."""
        if start is not None:
            self.send_command(f"sweep start {int(start)}\r")
        if stop is not None:
            self.send_command(f"sweep stop {int(stop)}\r")

    def set_frequency(self, freq: float):
        """Sets a single frequency on the device."""
        if freq is not None:
            self.send_command(f"freq {int(freq)}\r")

    def set_port(self, port: int):
        """
        Specifies which port to measure (port 0 or 1 for reflection,
        depending on the NanoVNA's configuration).
        """
        if port is not None:
            self.send_command(f"port {port}\r")

    def set_gain(self, gain: int):
        """Adjusts the device gain (if supported)."""
        if gain is not None:
            self.send_command(f"gain {gain} {gain}\r")

    def set_offset(self, offset: int):
        """Sets an offset level (if supported)."""
        if offset is not None:
            self.send_command(f"offset {offset}\r")

    def set_strength(self, strength: int):
        """Sets the output power level (if supported)."""
        if strength is not None:
            self.send_command(f"power {strength}\r")

    def fetch_data(self) -> str:
        """
        Reads lines from the device until it encounters the 'ch>' prompt.
        Returns the concatenated result as a single string.
        """
        result = ''
        line = ''
        while True:
            c = self.serial.read().decode('utf-8', errors='ignore')
            if c == '\r':
                continue  # ignore carriage returns
            line += c
            if c == '\n':
                result += line
                line = ''
            # 'ch>' is the prompt meaning no more data
            if line.endswith('ch>'):
                break
        return result

    def fetch_buffer(self, buffer: int = 0) -> np.ndarray:
        """
        Dumps raw buffer data from the NanoVNA, returning a NumPy int16 array.
        """
        self.send_command(f"dump {buffer}\r")
        data = self.fetch_data()
        x = []
        for line in data.split('\n'):
            line = line.strip()
            if line:
                x.extend(int(d, 16) for d in line.split(' '))
        return np.array(x, dtype=np.int16)

    def fetch_rawwave(self, freq: float = None):
        """
        Fetches raw wave data for reference and sample channels, returning
        two NumPy int16 arrays. Optionally sets the device to a specific freq.
        """
        if freq:
            self.set_frequency(freq)
            time.sleep(0.05)
        self.send_command("dump 0\r")
        data = self.fetch_data()
        x = []
        for line in data.split('\n'):
            line = line.strip()
            if line:
                x.extend(int(d, 16) for d in line.split(' '))
        ref = np.array(x[0::2], dtype=np.int16)
        samp = np.array(x[1::2], dtype=np.int16)
        return ref, samp

    def fetch_array(self, sel: int):
        """
        Fetches complex array data from the device for a given index (e.g. 0 or 1).
        Returns a NumPy array of complex values.
        """
        self.send_command(f"data {sel}\r")
        data = self.fetch_data()
        x = []
        for line in data.split('\n'):
            line = line.strip()
            if line:
                parts = line.split(' ')
                # real + j*imag
                x.append(float(parts[0]) + float(parts[1]) * 1j)
        return np.array(x)

    def fetch_gamma(self, freq: float = None) -> complex:
        """
        Sends the 'gamma' command to the device or sets freq first if provided.
        Returns the complex reflection coefficient.
        """
        if freq:
            self.set_frequency(freq)
        self.send_command("gamma\r")
        data = self.serial.readline().decode().strip().split(' ')
        # data[0], data[1] = real, imag integers
        val = (int(data[0]) + int(data[1]) * 1.j) / REF_LEVEL
        return val

    # The code below reuses the raw wave approach for reflection coefficient:
    def reflect_coeff_from_rawwave(self, freq: float = None) -> complex:
        """
        Captures reference and sample waveforms and computes an average reflection coefficient.
        Based on raw wave data + Hilbert transform (requires scipy.signal).
        """
        import scipy.signal as signal
        ref, samp = self.fetch_rawwave(freq)
        ref_hilbert = signal.hilbert(ref)
        # A simplified average-based reflection measurement:
        return np.average(ref_hilbert * samp / np.abs(ref_hilbert) / REF_LEVEL)

    reflect_coeff = reflect_coeff_from_rawwave  # Alias
    gamma = reflect_coeff_from_rawwave          # Another alias

    def resume(self):
        """Send 'resume' command to the device (resume scanning)."""
        self.send_command("resume\r")

    def pause(self):
        """Send 'pause' command to stop scanning/updates."""
        self.send_command("pause\r")

    def scan_gamma(self, port: int = None) -> np.ndarray:
        """
        Scans reflection coefficient (gamma) across self.frequencies
        by setting each frequency in turn. Slower but direct approach.
        """
        if self._frequencies is None:
            raise ValueError("Frequencies not set. Call set_frequencies() first.")
        self.set_port(port)
        values = []
        for f in self._frequencies:
            val = self.gamma(f)
            values.append(val)
        return np.array(values)

    def fetch_frequencies(self):
        """
        Commands the device to print out its internal frequency list,
        storing them in self._frequencies.
        """
        self.send_command("frequencies\r")
        data = self.fetch_data()
        x = []
        for line in data.split('\n'):
            line = line.strip()
            if line:
                x.append(float(line))
        self._frequencies = np.array(x)

    def send_scan(self, start: float = 1e6, stop: float = 900e6, points: int = None):
        """
        Commands the device to 'scan' a range of frequencies with a certain number of points.
        The device then updates its internal data arrays for each channel.
        """
        if points:
            self.send_command(f"scan {int(start)} {int(stop)} {points}\r")
        else:
            self.send_command(f"scan {int(start)} {int(stop)}\r")

    def scan(self):
        """
        If frequencies are set, scans in segments (each 101 points by default)
        for both channels (arrays 0 and 1) and returns them as a tuple of lists.
        """
        segment_length = 101
        array0 = []
        array1 = []
        if self._frequencies is None:
            self.fetch_frequencies()

        freqs = self._frequencies.copy()
        while len(freqs) > 0:
            seg_start = freqs[0]
            if len(freqs) >= segment_length:
                seg_stop = freqs[segment_length - 1]
                length = segment_length
            else:
                seg_stop = freqs[-1]
                length = len(freqs)

            # Request the device to scan this segment
            self.send_scan(seg_start, seg_stop, length)
            array0.extend(self.fetch_array(0))
            array1.extend(self.fetch_array(1))

            freqs = freqs[segment_length:]
        self.resume()
        return (array0, array1)

    def capture(self):
        """
        Captures the current NanoVNA screen (320x240, 16-bit 565 format) and
        returns a Pillow Image object (RGBA). Requires 'PIL' (Pillow) installed.
        """
        import struct
        from PIL import Image

        self.send_command("capture\r")
        # 320 * 240 * 2 bytes = 153600 bytes
        raw_bytes = self.serial.read(320 * 240 * 2)
        pixel_values = struct.unpack(">76800H", raw_bytes)

        # Convert 565 (RGB) to 8888 (RGBA)
        arr = np.array(pixel_values, dtype=np.uint32)
        arr = (
            0xFF000000
            + ((arr & 0xF800) >> 8)
            + ((arr & 0x07E0) << 5)
            + ((arr & 0x001F) << 19)
        )
        img = Image.frombuffer('RGBA', (320, 240), arr, 'raw', 'RGBA', 0, 1)
        return img

    # -------------
    # Example plotting methods
    # -------------
    def logmag(self, x: np.ndarray):
        """
        Example: Plot the log magnitude (20 * log10(|x|)) vs. frequency using matplotlib.
        """
        import matplotlib.pyplot as pl
        pl.grid(True)
        pl.xlim(self.frequencies[0], self.frequencies[-1])
        pl.plot(self.frequencies, 20 * np.log10(np.abs(x)))
        pl.xlabel("Frequency (Hz)")
        pl.ylabel("Magnitude (dB)")

    def vswr(self, x: np.ndarray):
        """
        Example: Plot VSWR from reflection coefficient data vs. frequency.
        VSWR = (1 + |Gamma|) / (1 - |Gamma|)
        """
        import matplotlib.pyplot as pl
        pl.grid(True)
        vswr = (1 + np.abs(x)) / (1 - np.abs(x))
        pl.xlim(self.frequencies[0], self.frequencies[-1])
        pl.plot(self.frequencies, vswr)
        pl.xlabel("Frequency (Hz)")
        pl.ylabel("VSWR")

    # Add more plotting/analysis methods as needed...


# ------------------------------------------------------------------------------
# OPTIONAL: If you want to keep a command-line interface in this same file,
# you can keep (or adapt) the 'if __name__ == "__main__":' section.
# Otherwise, remove it to make this a pure library module for Flask integration.
# ------------------------------------------------------------------------------
if __name__ == '__main__':
    import argparse
    import matplotlib.pyplot as plt

    parser = argparse.ArgumentParser(description="NanoVNA CLI Tool")
    parser.add_argument("--capture", help="Capture the NanoVNA screen to an image file")
    parser.add_argument("--start", type=float, default=1e6, help="Start frequency")
    parser.add_argument("--stop", type=float, default=900e6, help="Stop frequency")
    parser.add_argument("--points", type=int, default=101, help="Number of sweep points")
    parser.add_argument("--plot", action="store_true", help="Plot log magnitude data")
    parser.add_argument("--vswr", action="store_true", help="Plot VSWR")
    parser.add_argument("--port", type=int, default=0, help="Which port to use (0 or 1)")
    args = parser.parse_args()

    nv = NanoVNA()
    if args.capture:
        print("Capturing screen...")
        img = nv.capture()
        img.save(args.capture)
        print(f"Screen saved to {args.capture}")
    else:
        # Example usage: set frequencies, do a scan, and optionally plot
        nv.set_frequencies(args.start, args.stop, args.points)
        arr0, arr1 = nv.scan()  # two arrays for channel 0 and 1
        arr = arr0 if args.port == 0 else arr1

        if args.plot:
            nv.logmag(arr)
        if args.vswr:
            nv.vswr(arr)
        if args.plot or args.vswr:
            plt.show()
