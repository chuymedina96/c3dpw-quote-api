# quotes/serializers.py
from rest_framework import serializers

ALLOWED_EXTS = ("stl", "obj")
MAX_FILE_MB = 50

class QuoteParamsSerializer(serializers.Serializer):
    material = serializers.ChoiceField(
        choices=["PLA", "PLA+", "PETG", "Nylon", "CFNylon"],
        required=False, default="PLA"
    )
    layer_height_mm = serializers.FloatField(
        required=False, default=0.2, min_value=0.05, max_value=0.6
    )
    infill_pct = serializers.IntegerField(
        required=False, default=20, min_value=0, max_value=100
    )

class QuoteUploadSerializer(QuoteParamsSerializer):
    file = serializers.FileField(required=True)

    def validate_file(self, f):
        name = getattr(f, "name", "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ALLOWED_EXTS:
            raise serializers.ValidationError("Unsupported file type. Upload STL or OBJ.")
        size_ok = getattr(f, "size", None)
        if size_ok and size_ok > MAX_FILE_MB * 1024 * 1024:
            raise serializers.ValidationError(f"File too large (max {MAX_FILE_MB}MB).")
        # Optional: quick content-type guard (don’t rely solely on this)
        ct = getattr(f, "content_type", "") or ""
        if ct and not any(x in ct for x in ("stl", "obj", "octet-stream")):
            # Not fatal—comment this out if your browser always sends octet-stream
            pass
        return f
