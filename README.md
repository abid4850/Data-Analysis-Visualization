# DataViz Pro - Professional Data Analysis & Visualization Tool

A comprehensive web application built with Django for interactive data analysis and visualization. Upload your datasets or use built-in sample data to create stunning visualizations, perform statistical analysis, and generate insights without writing code.

## 🚀 Features

- **Interactive Data Visualization**: Create line charts, bar graphs, scatter plots, histograms, and KDE plots
- **File Upload Support**: Upload CSV and Excel files for instant analysis
- **Sample Datasets**: Pre-loaded datasets including Iris, Tips, Penguins, Flights, Titanic, and Car Crashes
- **Correlation Heatmaps**: Visualize relationships between variables
- **Pair Plots**: Explore multivariate relationships
- **Statistical Summaries**: Automatic data overview and descriptive statistics
- **Responsive Design**: Bootstrap 5 powered interface that works on all devices
- **Dark Mode**: Toggle between light and dark themes
- **SEO Optimized**: Built-in SEO features and sitemap generation
- **Blog Integration**: Content management system for articles and tutorials

## 🛠️ Technology Stack

- **Backend**: Django 5.2.9
- **Frontend**: Bootstrap 5, HTML5, CSS3, JavaScript
- **Data Processing**: Pandas, NumPy
- **Visualization**: Matplotlib, Seaborn, Plotly
- **Database**: SQLite (development), PostgreSQL (production)
- **Deployment**: Ready for Heroku, AWS, or any WSGI server

## 📋 Prerequisites

- Python 3.8+
- pip (Python package manager)
- Virtual environment (recommended)

## 🔧 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/dataviz-pro.git
   cd dataviz-pro
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations**
   ```bash
   cd DataVizProject
   python manage.py migrate
   ```

5. **Collect static files**
   ```bash
   python manage.py collectstatic --noinput
   ```

6. **Start the development server**
   ```bash
   python manage.py runserver
   ```

7. **Open your browser**
   Navigate to `http://127.0.0.1:8000/`

## 📖 Usage

1. **Home Page**: Overview of the application and quick start guide
2. **Analysis Page**: Upload data or select sample datasets for visualization
3. **Datasets Page**: Browse available sample datasets
4. **Tools**: Specialized tools for CSV visualization, data summaries, and chart generation
5. **Blog**: Read articles about data visualization best practices

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 Author

**Abid Hussain** - *Full Stack Developer*

- LinkedIn: [Your LinkedIn](https://linkedin.com/in/yourprofile)
- Portfolio: [Your Portfolio](https://yourportfolio.com)
- Email: your.email@example.com

## 🙏 Acknowledgments

- Django Framework
- Bootstrap 5
- Pandas, Matplotlib, Seaborn, Plotly
- Open source community

---

Made with ❤️ using Django & Python
