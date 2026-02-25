"""
ML Inference Module
Uses Multi-Scale TCN Autoencoder to detect depression risk from wearable sensor data.
Anomaly detection via reconstruction error — no labels needed during inference.
"""

import warnings
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path

# ===============================
# MULTI-SCALE TCN AUTOENCODER
# ===============================
class MultiScaleTCN_AE(nn.Module):
    def __init__(self, input_size=7):
        super().__init__()

        self.branch1 = nn.Conv1d(input_size, 32, kernel_size=3, padding=1)
        self.branch2 = nn.Conv1d(input_size, 32, kernel_size=5, padding=2)
        self.branch3 = nn.Conv1d(input_size, 32, kernel_size=7, padding=3)

        self.relu   = nn.LeakyReLU(0.1)
        self.merge  = nn.Conv1d(96, 64, kernel_size=1)
        self.expand = nn.Conv1d(64, 96, kernel_size=1)

        self.dec1 = nn.Conv1d(96, input_size, kernel_size=3, padding=1)
        self.dec2 = nn.Conv1d(96, input_size, kernel_size=5, padding=2)
        self.dec3 = nn.Conv1d(96, input_size, kernel_size=7, padding=3)

    def forward(self, x):
        # x: (batch, time, features) → permute for Conv1d
        x = x.permute(0, 2, 1)                        # (batch, features, time)

        b1 = self.relu(self.branch1(x))
        b2 = self.relu(self.branch2(x))
        b3 = self.relu(self.branch3(x))

        x      = torch.cat([b1, b2, b3], dim=1)       # (batch, 96, time)
        latent = self.relu(self.merge(x))              # (batch, 64, time)
        x      = self.relu(self.expand(latent))        # (batch, 96, time)

        d1 = self.dec1(x)
        d2 = self.dec2(x)
        d3 = self.dec3(x)

        recon = (d1 + d2 + d3) / 3.0                  # (batch, features, time)
        return recon.permute(0, 2, 1)                  # (batch, time, features)


# ===============================
# MODEL SINGLETON
# ===============================
class ModelSingleton:
    _instance = None
    _model    = None
    _scaler   = None
    _device   = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_files(self, models_dir):
        """Download model files from HuggingFace model repo if missing."""
        needed = {
            "ms_tcn_ae_model.pth.zip": "ms_tcn_ae_model.pth",
            "scaler.pkl":               "scaler.pkl",
        }
        missing = {k: v for k, v in needed.items()
                   if not (models_dir / k).exists()}
        if not missing:
            return

        from huggingface_hub import hf_hub_download
        models_dir.mkdir(parents=True, exist_ok=True)
        for local_name, hf_filename in missing.items():
            print(f"[ML] Downloading {hf_filename} from santa47/cbt-tcn-ae ...")
            downloaded = hf_hub_download(
                repo_id="santa47/cbt-tcn-ae",
                filename=hf_filename,
                repo_type="model",
                local_dir=str(models_dir),
                local_dir_use_symlinks=False,
            )
            # Rename if hf saved it under the hf_filename, not our local_name
            dest = models_dir / local_name
            src  = models_dir / hf_filename
            if src.exists() and not dest.exists():
                src.rename(dest)
            print(f"[ML] {local_name} ready.")

    def load_model(self):
        if self._model is not None:
            return self._model

        try:
            import joblib

            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            models_dir = Path(__file__).parent / "models"
            self._ensure_files(models_dir)

            # Load autoencoder weights
            model_path  = models_dir / "ms_tcn_ae_model.pth.zip"
            self._model = MultiScaleTCN_AE(input_size=7)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                state_dict = torch.load(model_path, map_location=self._device,
                                        weights_only=True)
            self._model.load_state_dict(state_dict)
            self._model.to(self._device)
            self._model.eval()

            # Load StandardScaler
            scaler_path  = models_dir / "scaler.pkl"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self._scaler = joblib.load(scaler_path)

            print(f"[ML] TCN-AE Model loaded successfully on {self._device}")
            return self._model

        except Exception as e:
            print(f"[ML] Error loading model: {str(e)}")
            raise

    def get_model(self):
        if self._model is None:
            self.load_model()
        return self._model

    def get_scaler(self):
        if self._scaler is None:
            self.load_model()
        return self._scaler

    def get_device(self):
        if self._device is None:
            self.load_model()
        return self._device


# Global singleton
model_singleton = ModelSingleton()


# ===============================
# FEATURE EXTRACTION
# ===============================

def extract_features_from_window(ppg_w, gsr_w, acc_w):
    """
    Extract 7 features from a window of raw (non-normalized) sensor samples.

    Features (same order the scaler was trained on):
      0  mean_gsr
      1  std_gsr
      2  slope_gsr
      3  mean_ppg
      4  std_ppg
      5  mean_motion
      6  motion_ratio
    """
    ppg_w = np.array(ppg_w, dtype=float)
    gsr_w = np.array(gsr_w, dtype=float)
    acc_w = np.array(acc_w, dtype=float)

    mean_gsr   = np.mean(gsr_w)
    std_gsr    = np.std(gsr_w)
    slope_gsr  = np.polyfit(range(len(gsr_w)), gsr_w, 1)[0] if len(gsr_w) > 1 else 0.0

    mean_ppg   = np.mean(ppg_w)
    std_ppg    = np.std(ppg_w)

    mean_motion  = np.mean(acc_w)
    motion_ratio = float(np.mean(np.abs(acc_w) > 0.2))

    return [mean_gsr, std_gsr, slope_gsr, mean_ppg, std_ppg, mean_motion, motion_ratio]


def prepare_sensor_data(raw_readings):
    """
    Prepare raw sensor readings for autoencoder inference.

    Args:
        raw_readings: list of dicts with keys ppg, gsr, acc_x, acc_y, acc_z
                      ordered oldest → newest (minimum 18)

    Returns:
        numpy array shape (1, 5, 7) scaled and ready for model, or None
    """
    if len(raw_readings) < 18:
        return None

    ppg_vals = [r['ppg']   for r in raw_readings]
    gsr_vals = [r['gsr']   for r in raw_readings]

    # Motion magnitude with gravity removed (matches ESP32 firmware)
    acc_vals = []
    for r in raw_readings:
        total  = np.sqrt(r['acc_x']**2 + r['acc_y']**2 + r['acc_z']**2)
        motion = abs(total - 9.81)
        acc_vals.append(motion)

    # 5 overlapping windows of 5 samples (stride 3 → fits 18 readings)
    WINDOW_SIZE = 5
    STRIDE      = 3
    start_idx   = len(raw_readings) - 18
    windows     = []

    for i in range(5):
        ws = start_idx + i * STRIDE
        we = ws + WINDOW_SIZE
        feat = extract_features_from_window(
            ppg_vals[ws:we], gsr_vals[ws:we], acc_vals[ws:we]
        )
        windows.append(feat)

    # shape (5, 7)
    feature_seq = np.array(windows, dtype=np.float32)

    # Scale using the fitted StandardScaler
    scaler = model_singleton.get_scaler()
    feature_seq = scaler.transform(feature_seq).astype(np.float32)

    # Add batch dimension → (1, 5, 7)
    return np.expand_dims(feature_seq, axis=0)


# ===============================
# RECONSTRUCTION ERROR THRESHOLD
# ===============================
THRESHOLD = 0.85


# ===============================
# PREDICTION
# ===============================

def predict_risk(raw_readings):
    """
    Predict depression risk using autoencoder reconstruction error.

    Args:
        raw_readings: list of recent sensor reading dicts (min 18)

    Returns:
        dict with prediction, risk_level, confidence, message  — or None on error
    """
    try:
        features = prepare_sensor_data(raw_readings)

        if features is None:
            return {
                "prediction":  "INSUFFICIENT_DATA",
                "risk_level":  -1,
                "confidence":  0.0,
                "message":     "Need at least 18 readings for prediction"
            }

        model  = model_singleton.get_model()
        device = model_singleton.get_device()

        x = torch.tensor(features, dtype=torch.float32).to(device)

        with torch.no_grad():
            recon = model(x)
            error = torch.mean((recon - x) ** 2).item()

        high_risk  = error > THRESHOLD
        risk_level = 2 if high_risk else 0
        prediction = "HIGH_RISK" if high_risk else "NORMAL"

        # Confidence: how far from the threshold (clamped 0-1)
        if high_risk:
            confidence = min(1.0, error / (2 * THRESHOLD))
        else:
            confidence = min(1.0, 1.0 - error / THRESHOLD)
        confidence = max(0.0, round(confidence, 3))

        messages = {
            0: "User appears to be in normal mental state",
            2: "Elevated stress/depression risk detected - monitoring recommended"
        }

        print(f"[ML] recon_error={error:.4f} threshold={THRESHOLD} -> {prediction} ({confidence:.0%})")

        return {
            "prediction":  prediction,
            "risk_level":  risk_level,
            "confidence":  confidence,
            "message":     messages[risk_level]
        }

    except Exception as e:
        print(f"[ML] Error during inference: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


# ===============================
# INITIALIZATION
# ===============================

def initialize_model():
    """Load model and scaler at startup."""
    try:
        model_singleton.load_model()
        return True
    except Exception as e:
        print(f"[ML] Model initialization failed: {str(e)}")
        return False
