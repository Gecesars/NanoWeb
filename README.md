<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>NanoWeb Project</title>
    <style>
      body {
        font-family: Arial, sans-serif;
        margin: 2em;
        line-height: 1.6;
      }
      .language-switch {
        position: fixed;
        top: 1em;
        right: 2em;
      }
      .language-switch a {
        margin-left: 1em;
        text-decoration: none;
        color: #007acc;
      }
      pre {
        background-color: #f4f4f4;
        padding: 1em;
        overflow-x: auto;
      }
      code {
        background-color: #eee;
        padding: 0.2em 0.4em;
        border-radius: 3px;
      }
      h1,
      h2,
      h3,
      h4,
      h5 {
        margin-top: 1.2em;
      }
      ul {
        margin-left: 2em;
      }
      a {
        color: #007acc;
        text-decoration: none;
      }
      a:hover {
        text-decoration: underline;
      }
    </style>
  </head>
  <body>
    <!-- Language Switch Placeholder -->
    <div class="language-switch">
      <strong>Language:</strong>
      <a href="#" title="Switch to Portuguese">Portuguese</a>
      <a href="#" title="Switch to Spanish">Spanish</a>
      <!-- Currently English -->
    </div>

    <h1>NanoWeb</h1>
    <p>
      NanoWeb is a comprehensive project focused on customizing and developing
      an advanced antenna testing system. This solution leverages a web server
      to capture, analyze, and share data related to antenna products from
      <a href="http://www.idealantenas.com.br" target="_blank">IdealAntenas</a>,
      providing a professional and user-friendly interface for antenna testing
      and data management.
    </p>

    <h2>Table of Contents</h2>
    <ul>
      <li><a href="#overview">Overview</a></li>
      <li><a href="#features">Features</a></li>
      <li><a href="#project-structure">Project Structure</a></li>
      <li><a href="#installation-and-setup">Installation and Setup</a></li>
      <li><a href="#usage">Usage</a></li>
      <li><a href="#development-workflow">Development Workflow</a></li>
      <li><a href="#contributing">Contributing</a></li>
      <li><a href="#license">License</a></li>
      <li><a href="#contact">Contact</a></li>
    </ul>

    <h2 id="overview">Overview</h2>
    <p>
      NanoWeb integrates customized firmware for antenna testing devices with a
      modern web interface. The primary objectives are:
    </p>
    <ul>
      <li>
        <strong>Advanced Radiation Diagram Measurement:</strong> In open-field
        scenarios, Time-Domain Reflectometry (TDR) is utilized to isolate the main
        signal from reflections, enabling extremely accurate and automated
        measurements. This ensures the superior quality standards for
        <a href="http://www.idealantenas.com.br" target="_blank">IdealAntenas</a>.
      </li>
      <li>
        <strong>Firmware Customization:</strong> Extend the NanoVNA firmware to
        include additional test commands, real-time data logging, and specialized
        calibration routines.
      </li>
      <li>
        <strong>Robust Data Analysis and Sharing:</strong> Develop a user-friendly
        Flask-based web server that processes, visualizes, and distributes
        collected data, facilitating remote collaboration and real-time insights.
      </li>
      <li>
        <strong>Automation and Efficiency:</strong> Provide comprehensive testing
        tools and automation features to accelerate antenna performance evaluation
        and streamline the entire testing process.
      </li>
    </ul>

    <h2 id="features">Features</h2>
    <ul>
      <li>
        <strong>Custom Firmware:</strong> Extended NanoVNA firmware with support
        for additional test commands, TDR-based measurements, and enhanced
        data logging.
      </li>
      <li>
        <strong>Open-Field Antenna Testing:</strong> Specialized workflows to
        measure antenna radiation diagrams in open-field scenarios, using TDR to
        isolate main signals from reflections.
      </li>
      <li>
        <strong>Web Server Integration:</strong> A Flask-based web server offering
        a clean, professional front-end to visualize test results, control test
        parameters, and manage device configurations.
      </li>
      <li>
        <strong>Data Sharing and Analysis:</strong> Capabilities to capture,
        analyze, and share real-time data from antenna testing, facilitating
        remote monitoring and collaboration.
      </li>
      <li>
        <strong>Modular Design:</strong> A well-organized repository that
        separates firmware, hardware documentation, and web server code for
        easier updates and contributions.
      </li>
    </ul>

    <h2 id="project-structure">Project Structure</h2>
    <pre>
NanoVNA/
├── Firmware/         # Source code and build files for the customized firmware
├── FlaskServer/      # Flask application for the web server, including templates and static files
├── hardware/         # Schematics, diagrams, and hardware-related documentation
└── README.md         # Project documentation (this file)
    </pre>

    <h2 id="installation-and-setup">Installation and Setup</h2>
    <h3>Firmware</h3>
    <ol>
      <li>
        <strong>Prerequisites:</strong>
        <ul>
          <li>ARM toolchain (arm-none-eabi-gcc, etc.)</li>
          <li>DFU utilities (<code>dfu-util</code>)</li>
          <li>ChibiOS source (configured as a submodule)</li>
        </ul>
      </li>
      <li>
        <strong>Building the Firmware:</strong>
        <pre>
cd Firmware
make clean       # Optional: Clean previous builds
make             # Compile the firmware
        </pre>
      </li>
      <li>
        <strong>Flashing the Firmware:</strong>
        <pre>
make flash
        </pre>
        <p>
          Ensure your device is connected and properly configured in the
          Makefile.
        </p>
      </li>
    </ol>

    <h3>Web Server (Flask)</h3>
    <ol>
      <li>
        <strong>Prerequisites:</strong>
        <ul>
          <li>Python 3.x installed</li>
          <li>Virtual environment tool (<code>venv</code>)</li>
        </ul>
      </li>
      <li>
        <strong>Setup:</strong>
        <pre>
cd FlaskServer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
        </pre>
      </li>
      <li>
        <strong>Running the Server:</strong>
        <pre>
python app.py
        </pre>
        <p>
          The server will start (by default at
          <a href="http://127.0.0.1:5000" target="_blank">http://127.0.0.1:5000</a>),
          and you can access the web interface via your browser.
        </p>
      </li>
    </ol>

    <h2 id="usage">Usage</h2>
    <ul>
      <li>
        <strong>Open-Field Testing:</strong> Deploy the system in an open field
        environment for highly accurate radiation diagram measurements. Use TDR
        modes to isolate the main signal from reflections, ensuring precise and
        automated antenna analysis.
      </li>
      <li>
        <strong>Firmware Testing:</strong> After building and flashing the
        firmware, use the dedicated test commands (customized for your antenna
        testing needs) to evaluate the performance of antennas from
        <a href="http://www.idealantenas.com.br" target="_blank">IdealAntenas</a>.
      </li>
      <li>
        <strong>Web Interface:</strong> Access the Flask web server to view test
        data, generate reports, and configure automated tests. The interface
        includes:
        <ul>
          <li>Real-time data visualization</li>
          <li>Test automation controls</li>
          <li>Historical data logs and analysis tools</li>
        </ul>
      </li>
    </ul>

    <h2 id="development-workflow">Development Workflow</h2>
    <ol>
      <li>
        <strong>Cloning the Repository:</strong>
        <pre>
git clone https://github.com/Gecesars/NanoWeb.git
cd NanoWeb
        </pre>
      </li>
      <li>
        <strong>Branching:</strong>
        <pre>
git checkout -b feature/your-feature-name
        </pre>
      </li>
      <li>
        <strong>Committing Changes:</strong>
        <p>
          Make small, atomic commits with clear messages.
        </p>
      </li>
      <li>
        <strong>Merging:</strong>
        <p>
          Open a pull request on GitHub and merge changes after review.
        </p>
      </li>
      <li>
        <strong>Tagging Releases:</strong>
        <pre>
git tag -a v1.0 -m "Release version 1.0"
git push origin --tags
        </pre>
      </li>
    </ol>

    <h2 id="contributing">Contributing</h2>
    <p>Contributions are welcome! Please follow these guidelines:</p>
    <ul>
      <li>Fork the repository and create your branch from <code>main</code>.</li>
      <li>Write clear commit messages.</li>
      <li>Document new features in this README as needed.</li>
      <li>Submit pull requests for review.</li>
    </ul>

    <h2 id="license">License</h2>
    <p>
      This project is licensed under the
      <a href="LICENSE">MIT License</a>.
    </p>

    <h2 id="contact">Contact</h2>
    <p>If you have any questions, suggestions, or issues, please feel free to contact:</p>
    <ul>
      <li>
        Email: <a href="mailto:gecesars@gmail.com">gecesars@gmail.com</a>
      </li>
      <li>
        Email:
        <a href="mailto:engenharia@idealantenas.com.br"
          >engenharia@idealantenas.com.br</a
        >
      </li>
    </ul>
  </body>
</html>
