"""
Cognitive Distortion Classifier
Uses TinyBERT model from HuggingFace
"""

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch.nn.functional as F


class DistortionClassifier:
    """
    Classifies text into cognitive distortion groups.
    
    Groups:
    - G0: No Distortion
    - G1: Binary & Global Evaluation (All-or-nothing, Labeling)
    - G2: Overgeneralized Beliefs (Overgeneralization, Mind Reading, Fortune-telling)
    - G3: Attentional Bias (Mental Filter, Magnification)
    - G4: Self-Referential Reasoning (Emotional Reasoning, Personalization, Should statements)
    """
    
    MODEL_NAME = "santa47/cbt-distortion-classifier-bert"
    
    def __init__(self):
        print(f"Loading classifier from {self.MODEL_NAME}...")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device}")
        
        self.tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.MODEL_NAME)
        self.model.to(self.device)
        self.model.eval()
        
        # Label mapping
        self.id_to_label = {
            0: "G0",
            1: "G1", 
            2: "G2",
            3: "G3",
            4: "G4"
        }
        
        self.label_info = {
            "G0": {
                "name": "No Distortion Detected",
                "description": "Healthy, balanced thinking",
                "distortions": []
            },
            "G1": {
                "name": "Binary & Global Evaluation",
                "description": "All-or-nothing thinking patterns",
                "distortions": ["All-or-nothing thinking", "Labeling"]
            },
            "G2": {
                "name": "Overgeneralized Beliefs",
                "description": "Making broad conclusions from limited evidence",
                "distortions": ["Overgeneralization", "Mind Reading", "Fortune-telling"]
            },
            "G3": {
                "name": "Attentional & Salience Bias",
                "description": "Focusing on negatives, ignoring positives",
                "distortions": ["Mental Filter", "Magnification"]
            },
            "G4": {
                "name": "Self-Referential & Emotion-Driven",
                "description": "Letting emotions drive conclusions",
                "distortions": ["Emotional Reasoning", "Personalization", "Should statements"]
            }
        }
        
        print("✅ Classifier loaded successfully!")
    
    def classify(self, text: str) -> dict:
        """
        Classify text into a distortion group.
        
        Args:
            text: Input text to classify
            
        Returns:
            dict with group, confidence, and group info
        """
        # Tokenize
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Predict
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probabilities = F.softmax(logits, dim=-1)
            
            predicted_class = torch.argmax(probabilities, dim=-1).item()
            confidence = probabilities[0][predicted_class].item()
        
        # Get group label
        group = self.id_to_label.get(predicted_class, "G0")
        group_info = self.label_info.get(group, {})
        
        return {
            "group": group,
            "confidence": round(confidence, 4),
            "group_name": group_info.get("name", "Unknown"),
            "description": group_info.get("description", ""),
            "distortions": group_info.get("distortions", []),
            "all_probabilities": {
                self.id_to_label[i]: round(probabilities[0][i].item(), 4)
                for i in range(len(self.id_to_label))
            }
        }
    
    def get_group_info(self, group: str) -> dict:
        """Get detailed info about a distortion group."""
        return self.label_info.get(group, {})


# Test if run directly
if __name__ == "__main__":
    classifier = DistortionClassifier()
    
    test_texts = [
        "I failed my exam. I'll never succeed at anything.",
        "My friend didn't text back. She must hate me.",
        "I made one mistake so the whole project is ruined.",
        "I feel anxious so something bad must be happening.",
        "I had a nice day today and enjoyed my lunch."
    ]
    
    print("\n🧪 Testing classifier:\n")
    for text in test_texts:
        result = classifier.classify(text)
        print(f"Text: {text[:50]}...")
        print(f"  → {result['group']}: {result['group_name']}")
        print(f"  → Confidence: {result['confidence']}")
        print()
