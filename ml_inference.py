"""
ML Inference Module
Uses Multi-Scale TCN model to predict depression risk from wearable sensor data
"""

import numpy as np
import torch
import torch.nn as nn
from pathlib import Path

# ===============================
# MULTI-SCALE TCN MODEL
# ===============================
class MultiScaleTCN(nn.Module):
    def __init__(self, input_size=7, num_classes=3):
        super().__init__()

        self.branch1 = nn.Conv1d(input_size, 32, kernel_size=3, padding=1)
        self.branch2 = nn.Conv1d(input_size, 32, kernel_size=5, padding=2)
        self.branch3 = nn.Conv1d(input_size, 32, kernel_size=7, padding=3)

        self.relu = nn.ReLU()
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(96, num_classes)

    def forward(self, x):
        x = x.permute(0, 2, 1)

        b1 = self.relu(self.branch1(x))
        b2 = self.relu(self.branch2(x))
        b3 = self.relu(self.branch3(x))

        x = torch.cat([b1, b2, b3], dim=1)
        x = self.pool(x).squeeze(-1)
        return self.fc(x)


# ===============================
# MODEL SINGLETON
# ===============================
class ModelSingleton:
    _instance = None
    _model = None
    _device = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_model(self):
        """Load the trained TCN model"""
        if self._model is not None:
            return self._model

        try:
            # Determine device
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            # Initialize model
            self._model = MultiScaleTCN(input_size=7, num_classes=3)

            # Load weights
            model_path = Path(__file__).parent / "models" / "multiscale_tcn.pth"
            state_dict = torch.load(model_path, map_location=self._device)
            self._model.load_state_dict(state_dict)

            self._model.to(self._device)
            self._model.eval()

            print(f"✅ TCN Model loaded successfully on {self._device}")
            return self._model

        except Exception as e:
            print(f"❌ Error loading TCN model: {str(e)}")
            raise

    def get_model(self):
        if self._model is None:
            return self.load_model()
        return self._model

    def get_device(self):
        if self._device is None:
            self.load_model()
        return self._device


# Global model instance
model_singleton = ModelSingleton()


# ===============================
# FEATURE EXTRACTION
# ===============================

def z_normalize(values):
    """Z-normalize a sequence of values"""
    values = np.array(values)
    mean = np.mean(values)
    std = np.std(values)

    # Avoid division by zero
    if std < 1e-6:
        return np.zeros_like(values)

    return (values - mean) / std


def extract_features_from_window(window_data):
    """
    Extract 7 features from a 5-sample window

    Args:
        window_data: dict with keys 'z_gsr', 'z_ppg', 'z_acc' (each is list of 5 values)

    Returns:
        list of 7 features: [mean_gsr, std_gsr, slope_gsr, mean_ppg, std_ppg, mean_motion, motion_ratio]
    """
    z_gsr = np.array(window_data['z_gsr'])
    z_ppg = np.array(window_data['z_ppg'])
    z_acc = np.array(window_data['z_acc'])

    # GSR features
    mean_gsr = np.mean(z_gsr)
    std_gsr = np.std(z_gsr)
    slope_gsr = np.polyfit(range(len(z_gsr)), z_gsr, 1)[0] if len(z_gsr) > 1 else 0.0

    # PPG features
    mean_ppg = np.mean(z_ppg)
    std_ppg = np.std(z_ppg)

    # Motion features
    mean_motion = np.mean(z_acc)
    motion_ratio = np.mean(np.abs(z_acc) > 0.2)  # Threshold from training

    return [mean_gsr, std_gsr, slope_gsr, mean_ppg, std_ppg, mean_motion, motion_ratio]


def prepare_sensor_data(raw_readings):
    """
    Prepare raw sensor readings for model inference

    Args:
        raw_readings: List of dicts, each containing:
            {ppg, gsr, acc_x, acc_y, acc_z, timestamp}
            Ordered from oldest to newest

    Returns:
        numpy array of shape (1, 5, 7) ready for model input
        or None if insufficient data
    """
    if len(raw_readings) < 25:  # Need at least 5 windows of 5 samples
        return None

    # Extract raw values
    ppg_values = [r['ppg'] for r in raw_readings]
    gsr_values = [r['gsr'] for r in raw_readings]

    # Calculate motion magnitude — subtract 9.81 to remove gravity offset,
    # matching the ESP32 firmware: acc_motion = abs(acc_total - 9.81)
    acc_values = []
    for r in raw_readings:
        total = np.sqrt(r['acc_x']**2 + r['acc_y']**2 + r['acc_z']**2)
        motion = abs(total - 9.81)
        acc_values.append(motion)

    # Z-normalize using rolling window statistics
    z_ppg = z_normalize(ppg_values)
    z_gsr = z_normalize(gsr_values)
    z_acc = z_normalize(acc_values)

    # Create 5-sample windows
    WINDOW_SIZE = 5
    windows = []

    # Use last 25 samples to create 5 non-overlapping windows
    start_idx = len(raw_readings) - 25

    for i in range(5):
        window_start = start_idx + (i * WINDOW_SIZE)
        window_end = window_start + WINDOW_SIZE

        window_data = {
            'z_gsr': z_gsr[window_start:window_end],
            'z_ppg': z_ppg[window_start:window_end],
            'z_acc': z_acc[window_start:window_end]
        }

        features = extract_features_from_window(window_data)
        windows.append(features)

    # Convert to numpy array: shape (5, 7)
    feature_sequence = np.array(windows)

    # Add batch dimension: shape (1, 5, 7)
    feature_sequence = np.expand_dims(feature_sequence, axis=0)

    return feature_sequence


def simple_standardize(features):
    """
    Simple feature normalization (since we don't have original StandardScaler params)
    Uses robust scaling to handle outliers
    """
    features = features.copy()

    # Robust scaling using median and IQR
    for i in range(features.shape[-1]):
        feature_col = features[0, :, i]
        median = np.median(feature_col)
        q75 = np.percentile(feature_col, 75)
        q25 = np.percentile(feature_col, 25)
        iqr = q75 - q25

        if iqr > 1e-6:
            features[0, :, i] = (feature_col - median) / iqr
        else:
            features[0, :, i] = 0

    return features


# ===============================
# PREDICTION
# ===============================

RISK_LABELS = {
    0: "NORMAL",
    1: "MILD_STRESS",
    2: "HIGH_STRESS"
}


def predict_risk(raw_readings):
    """
    Predict depression risk from raw sensor readings

    Args:
        raw_readings: List of recent sensor readings (minimum 25)

    Returns:
        dict with:
            - prediction: "NORMAL", "MILD_STRESS", or "HIGH_STRESS"
            - risk_level: 0, 1, or 2
            - confidence: float (0-1)
            - message: human-readable message
        or None if insufficient data
    """
    try:
        # Prepare data
        features = prepare_sensor_data(raw_readings)

        if features is None:
            return {
                "prediction": "INSUFFICIENT_DATA",
                "risk_level": -1,
                "confidence": 0.0,
                "message": "Need at least 25 readings for prediction"
            }

        # NOTE: simple_standardize is intentionally NOT called here.
        # Features are already extracted from z-normalized sensor data inside
        # prepare_sensor_data → z_normalize → extract_features_from_window.
        # Applying a second normalization pass corrupts the feature distributions
        # the model was trained on and causes systematic misclassification.

        # Convert to tensor
        model = model_singleton.get_model()
        device = model_singleton.get_device()

        x = torch.tensor(features, dtype=torch.float32).to(device)

        # Inference
        with torch.no_grad():
            output = model(x)
            probabilities = torch.softmax(output, dim=1)
            predicted_class = torch.argmax(probabilities, dim=1).item()
            confidence = probabilities[0, predicted_class].item()

        prediction_label = RISK_LABELS[predicted_class]

        # Create response
        messages = {
            0: "User appears to be in normal mental state",
            1: "Mild stress detected - monitoring recommended",
            2: "High stress/depression risk detected - intervention needed"
        }

        return {
            "prediction": prediction_label,
            "risk_level": predicted_class,
            "confidence": round(confidence, 3),
            "message": messages[predicted_class]
        }

    except Exception as e:
        print(f"❌ Error during ML prediction: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


# ===============================
# INITIALIZATION
# ===============================

def initialize_model():
    """Initialize the model at startup"""
    try:
        model_singleton.load_model()
        return True
    except Exception as e:
        print(f"⚠️  ML model initialization failed: {str(e)}")
        return False
