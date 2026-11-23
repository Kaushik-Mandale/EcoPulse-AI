class AIService:
    @staticmethod
    def verify_waste_image(image_url: str = None, waste_type: str = "Mixed Waste"):
        return {
            "status": "Pending Review",
            "confidence": None,
            "detected_type": None
        }
