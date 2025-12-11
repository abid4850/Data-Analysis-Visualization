# DataViz Pro: Interactive Data Analysis and Visualization Web App

## Overview

**DataViz Pro** is a professional, interactive web application built with the Django framework for data analysis and visualization. It allows users to upload their own CSV or XLSX files or select from a set of popular sample datasets (Iris, Titanic, Tips, Diamonds) to instantly generate comprehensive data overviews and a variety of visualizations, including:

*   **Dataset Overview:** Shape, data types, missing values, and summary statistics.
*   **Correlation Heatmap:** An interactive Plotly chart to visualize feature correlation.
*   **Pairplot (Scatter Matrix):** A Seaborn-generated plot to show pairwise relationships between variables, with optional hue grouping.
*   **Interactive Column Plot:** A customizable plot (Line, Bar, Scatter, Histogram, KDE) between any two numeric columns.

The application is designed with a modern, responsive user interface using **Bootstrap 5** for excellent UI/UX and is optimized for search engines (SEO).

## Features

*   **Data Source Flexibility:** Load sample datasets or upload custom CSV/XLSX files.
*   **Comprehensive Data Overview:** Quick access to key dataset metrics.
*   **Interactive Visualizations:** Utilizes Plotly for interactive heatmaps and Matplotlib/Seaborn for static plots.
*   **Responsive Design:** Built with Bootstrap 5 for a seamless experience on all devices.
*   **SEO Optimized:** Includes meta tags for better search engine ranking.

## Prerequisites

To run this project, you need:

*   Python 3.8+
*   `pip` (Python package installer)

## Installation and Setup

Follow these steps to get your development environment running:

1.  **Clone the repository (or create the project structure):**
    \`\`\`bash
    # Assuming you have the project files
    cd DataVizProject
    \`\`\`

2.  **Create and activate a virtual environment:**
    \`\`\`bash
    python3 -m venv venv
    source venv/bin/activate  # On Linux/macOS
    # venv\Scripts\activate   # On Windows
    \`\`\`

3.  **Install the required dependencies:**
    \`\`\`bash
    pip install -r ../requirements.txt
    \`\`\`

4.  **Run Django migrations:**
    \`\`\`bash
    python manage.py migrate
    \`\`\`

5.  **Start the development server:**
    \`\`\`bash
    python manage.py runserver
    \`\`\`

The application will be available at `http://127.0.0.1:8000/`.

## Project Structure

\`\`\`
DataVizProject/
├── DataVizProject/           # Project settings and configuration
│   ├── settings.py
│   ├── urls.py
│   └── ...
├── dataviz/                  # Main application
│   ├── migrations/
│   ├── templates/
│   │   └── dataviz/
│   │       ├── base.html     # Base template with Bootstrap 5
│   │       └── analysis.html # Main analysis page
│   ├── data_processor.py     # Core logic for data handling and plotting
│   ├── views.py              # Django view functions
│   ├── urls.py               # App URL patterns
│   └── ...
├── static/                   # Static files (CSS, JS, Images)
│   └── css/
│       └── style.css
├── media/                    # Uploaded files will be stored here
├── manage.py
└── requirements.txt          # Project dependencies
\`\`\`

## Technology Stack

*   **Backend Framework:** Django
*   **Frontend:** HTML5, CSS3, JavaScript
*   **Styling:** Bootstrap 5
*   **Data Handling:** Pandas, NumPy
*   **Visualization:** Matplotlib, Seaborn, Plotly
*   **File Handling:** OpenPyXL, Pillow
