import os
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.middleware.proxy_fix import ProxyFix
from db import db

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "smartgrid-dev-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///smartgrid.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize DB
db.init_app(app)

# Import routes after app is created to avoid circular imports
from models import GridData, ForecastData, PowerOutage
from api_client import CEAClient
from forecasting import DemandForecaster
import utils

from renewable_routes import renewable_bp
app.register_blueprint(renewable_bp)

cea_client = CEAClient()
forecaster = DemandForecaster()
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    try:
        grid_summary = utils.get_grid_summary()
        return render_template('dashboard.html', grid_summary=grid_summary)
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        flash(f"Error loading dashboard: {str(e)}", "danger")
        return render_template('dashboard.html', grid_summary=None)

@app.route('/api/grid-data')
def get_grid_data():
    try:
        data = cea_client.get_latest_power_data()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Error fetching grid data: {str(e)}")
        fallback_data = cea_client._get_fallback_power_data()
        return jsonify({"success": True, "data": fallback_data})

@app.route('/forecasting')
def forecasting_view():
    return render_template('forecasting.html')

@app.route('/api/forecast-demand', methods=['POST'])
def forecast_demand():
    try:
        days = int(request.form.get('days', 7))
        region = request.form.get('region', 'all')
        historical_data = cea_client.get_historical_data(region)
        forecast_result = forecaster.forecast_demand(historical_data, days)

        if not forecast_result.get("success", False) and "fallback_forecast" in forecast_result:
            return jsonify({"success": True, "forecast": forecast_result["fallback_forecast"]})

        if "forecast" in forecast_result:
            return jsonify({"success": True, "forecast": forecast_result["forecast"]})
        else:
            return jsonify({"success": True, "forecast": forecast_result})
    except Exception as e:
        logger.error(f"Error generating forecast: {str(e)}")
        fallback = forecaster._get_fallback_forecast(days)
        return jsonify({"success": True, "forecast": fallback})

@app.route('/load-balancing')
def load_balancing():
    return render_template('load_balancing.html')

@app.route('/api/simulate-balancing', methods=['POST'])
def simulate_balancing():
    try:
        scenario = request.json.get('scenario', 'normal')
        regions = request.json.get('regions', [])
        result = utils.simulate_load_balancing(scenario, regions)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        logger.error(f"Error in load balancing simulation: {str(e)}")
        result = utils.simulate_load_balancing('normal', [])
        return jsonify({"success": True, "result": result})

@app.route('/fault-detection')
def fault_detection():
    return render_template('fault_detection.html')

@app.route('/api/detect-faults')
def detect_faults():
    try:
        grid_status = cea_client.get_grid_status()
        faults = utils.detect_grid_faults(grid_status)
        return jsonify({"success": True, "faults": faults})
    except Exception as e:
        logger.error(f"Error in fault detection: {str(e)}")
        grid_status = cea_client._get_fallback_grid_status()
        faults = grid_status.get("potential_issues", [])
        return jsonify({"success": True, "faults": faults})

@app.route('/renewable-sources')
def renewable_sources():
    return render_template('renewable_sources.html')

# Initialize database
with app.app_context():
    db.create_all()
    logger.info("Database tables created")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)