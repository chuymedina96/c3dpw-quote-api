# quotes/utils/quote_engine.py
import io, os, trimesh

# Realistic bulk rates ($/g)
MATERIAL_RATES = {
    "PLA": 0.025,
    "PLA+": 0.028,
    "PETG": 0.030,
    "Nylon": 0.060,
    "CFNylon": 0.100,
}

# Densities (g/cm^3)
DENSITY_G_CM3 = {
    "PLA": 1.24, "PLA+": 1.24, "PETG": 1.27, "Nylon": 1.15, "CFNylon": 1.20
}

# Per-material presets (layer height hint + relative speed)
MATERIAL_PRESETS = {
    "PLA":     {"rec_layer_mm": 0.20, "speed_factor": 1.00},
    "PLA+":    {"rec_layer_mm": 0.20, "speed_factor": 0.95},
    "PETG":    {"rec_layer_mm": 0.24, "speed_factor": 0.85},
    "Nylon":   {"rec_layer_mm": 0.24, "speed_factor": 0.80},
    "CFNylon": {"rec_layer_mm": 0.28, "speed_factor": 0.70},
}

# Printer profiles (volumetric throughput in cm^3/hr)
MACHINE_PROFILES = {
    # Tuned higher so small/medium parts don't overestimate
    "BLENDED":                      {"label": "Blended (FF 5M Pro + Kobra S1)", "cm3_per_hr": 46.0, "hourly_rate": 8.0},
    "FlashForge Adventurer 5M Pro": {"label": "FlashForge Adventurer 5M Pro",   "cm3_per_hr": 50.0, "hourly_rate": 8.0},
    "Anycubic Kobra S1":            {"label": "Anycubic Kobra S1",              "cm3_per_hr": 42.0, "hourly_rate": 8.0},
}

DEFAULTS = {"material": "PLA", "layer_height_mm": 0.20, "infill_pct": 20, "machine": "BLENDED"}

HOURLY_RATE_FALLBACK = 8.0
BASE_FEE = 5.0
POSTPROCESS_FEE = 0.0

def _estimate_time_hours(volume_cm3, layer_mm, infill_pct, machine_speed_cm3_hr, material_speed_factor=1.0):
    """
    Estimate time using a volumetric throughput model, scaled by:
      - material speed_factor
      - layer height (coarser -> faster), modest effect
      - infill multiplier (more infill -> longer)
    """
    # Modest layer effect around 0.20mm reference
    layer_rel = 0.20 / max(layer_mm, 0.10)
    layer_rel = max(0.6, min(layer_rel, 1.5))  # slightly wider clamp

    # Gentler infill penalty so small parts don't blow up
    infill_mult = 1.0 + (infill_pct / 100.0) * 0.3

    effective_speed = max(1e-6, machine_speed_cm3_hr * material_speed_factor / layer_rel)
    est = (volume_cm3 / effective_speed) * infill_mult
    return max(0.08, est)  # ~5 minutes floor

def _price(rate_per_g, grams, time_hr, hourly_rate):
    return round(BASE_FEE + grams * rate_per_g + time_hr * hourly_rate + POSTPROCESS_FEE, 2)

def run_quote_engine(file_obj, material=None, layer_height_mm=None, infill_pct=None, machine=None):
    material = material or DEFAULTS["material"]
    layer_height_mm = float(layer_height_mm or DEFAULTS["layer_height_mm"])
    infill_pct = int(infill_pct or DEFAULTS["infill_pct"])
    machine = (machine or DEFAULTS["machine"])

    # resolve machine profile
    mprof = MACHINE_PROFILES.get(machine, MACHINE_PROFILES["BLENDED"])
    cm3_per_hr = float(mprof["cm3_per_hr"])
    hourly_rate = float(mprof.get("hourly_rate", HOURLY_RATE_FALLBACK))

    name = getattr(file_obj, "name", "part")
    ext = os.path.splitext(name)[1].lower()
    if ext not in [".stl", ".obj"]:
        raise ValueError("Unsupported file type. Upload STL or OBJ.")

    data = file_obj.read()
    mesh = trimesh.load(io.BytesIO(data), file_type=ext.replace(".", ""), force="mesh")
    if mesh.is_empty:
        raise ValueError("Mesh appears empty or invalid.")

    try:
        mesh.remove_duplicate_faces()
        mesh.remove_degenerate_faces()
        mesh.remove_unreferenced_vertices()
        mesh.process(validate=True)
    except Exception:
        pass

    # Geometry (mm -> cm)
    volume_cm3 = float(mesh.volume) / 1000.0
    surface_cm2 = float(mesh.area) / 100.0
    bbox_mm = [float(x) for x in mesh.extents.tolist()]
    triangles = int(getattr(mesh, "faces", []).__len__())

    # Initial material calc (for backward compatibility)
    dens = DENSITY_G_CM3.get(material, DENSITY_G_CM3["PLA"])
    rate = MATERIAL_RATES.get(material, MATERIAL_RATES["PLA"])
    mat_preset = MATERIAL_PRESETS.get(material, MATERIAL_PRESETS["PLA"])

    est_g = volume_cm3 * dens
    est_time = _estimate_time_hours(
        volume_cm3,
        layer_height_mm,
        infill_pct,
        machine_speed_cm3_hr=cm3_per_hr,
        material_speed_factor=mat_preset["speed_factor"],
    )
    price = _price(rate, est_g, est_time, hourly_rate=hourly_rate)

    # Client-side knobs (so material switch is instant)
    materials = {
        m: {
            "label": m,
            "rate_per_g": MATERIAL_RATES[m],
            "density_g_cm3": DENSITY_G_CM3[m],
            "rec_layer_mm": MATERIAL_PRESETS[m]["rec_layer_mm"],
            "speed_factor": MATERIAL_PRESETS[m]["speed_factor"],
        }
        for m in MATERIAL_RATES.keys()
    }

    pricing_model = {
        "base_fee": BASE_FEE,
        "hourly_rate": hourly_rate,
        "postprocess_fee": POSTPROCESS_FEE,
        "machine_cm3_per_hr": cm3_per_hr,
        "machine_label": mprof["label"],
        "machine_key": machine,
    }

    # Optional debug to help calibrate (safe to remove later)
    debug = {
        "calc": {
            "layer_rel": max(0.6, min(0.20 / max(layer_height_mm, 0.10), 1.5)),
            "infill_mult": 1.0 + (infill_pct / 100.0) * 0.3,
            "cm3_per_hr_used": cm3_per_hr,
            "material_speed_factor": mat_preset["speed_factor"],
        }
    }

    return {
        "filename": name,
        "material": material,
        "layer_height_mm": round(layer_height_mm, 3),
        "infill_pct": int(infill_pct),

        "volume_cm3": round(volume_cm3, 2),
        "surface_cm2": round(surface_cm2, 2),
        "bbox_mm": [round(x, 2) for x in bbox_mm],
        "triangles": triangles,

        "est_material_g": round(est_g, 1),
        "est_print_time_hr": round(est_time, 2),
        "price_usd": price,

        "materials": materials,
        "pricing_model": pricing_model,
        "debug": debug,
    }
