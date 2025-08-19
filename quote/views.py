# quotes/views.py
import os
import tempfile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, parsers
from django.http import JsonResponse
from .serializers import QuoteUploadSerializer
from .utils.quote_engine import run_quote_engine

# Accept large files; cap controlled by DATA_UPLOAD_MAX_MB in settings/env
MAX_MB = int(os.environ.get("DATA_UPLOAD_MAX_MB", "200"))


def health(_request):
    return JsonResponse({"status": "ok"})


class QuoteAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def post(self, request, *args, **kwargs):
        serializer = QuoteUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        upload = v["file"]
        material = v.get("material", "PLA")
        layer_height_mm = v.get("layer_height_mm", 0.2)
        infill_pct = v.get("infill_pct", 20)

        # Stream upload to a temp file so big STL/OBJ don't sit in RAM
        suffix = os.path.splitext(getattr(upload, "name", "part.stl"))[1].lower() or ".stl"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            temp_path = tmp.name

        try:
            with open(temp_path, "rb") as fh:
                result = run_quote_engine(
                    file_obj=fh,
                    material=material,
                    layer_height_mm=layer_height_mm,
                    infill_pct=infill_pct,
                )

            # Ensure we don't leak the tmp path; return the user's filename
            orig_name = getattr(upload, "name", None)
            if orig_name:
                result["filename"] = os.path.basename(orig_name)

            return Response(result, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Failed to parse mesh: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass


# ---- Batch pricing ----

def _tiers_from_env():
    tiers = [int(x) for x in os.environ.get("BATCH_TIERS", "1,10,25,50,100").split(",")]
    discounts = [float(x) for x in os.environ.get("DISCOUNTS", "0,0.05,0.08,0.12,0.15").split(",")]
    if len(discounts) != len(tiers):
        discounts = [0.0] * len(tiers)
    return tiers, discounts


class BatchQuoteAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def post(self, request, *args, **kwargs):
        serializer = QuoteUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        upload = v["file"]
        material = v.get("material", "PLA")
        layer_height_mm = v.get("layer_height_mm", 0.2)
        infill_pct = v.get("infill_pct", 20)

        # Stream to temp file (same pattern)
        suffix = os.path.splitext(getattr(upload, "name", "part.stl"))[1].lower() or ".stl"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            temp_path = tmp.name

        try:
            with open(temp_path, "rb") as fh:
                single = run_quote_engine(
                    file_obj=fh,
                    material=material,
                    layer_height_mm=layer_height_mm,
                    infill_pct=infill_pct,
                )

            # Ensure original filename is returned (not the temp path)
            orig_name = getattr(upload, "name", None)
            if orig_name:
                single["filename"] = os.path.basename(orig_name)

            base_unit = float(single["price_usd"])
            tiers, discounts = _tiers_from_env()
            rows = []
            for qty, disc in zip(tiers, discounts):
                per_unit = round(base_unit * (1 - disc), 2)
                total = round(per_unit * qty, 2)
                rows.append({"qty": qty, "discount": disc, "per_unit": per_unit, "total": total})

            return Response({"single": single, "tiers": rows}, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Failed to parse mesh: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass
