# onnxruntime must be imported before PyMuPDF / OpenCV. On machines with an old system
# Visual C++ runtime, those libraries load it first and onnxruntime then crashes.
try:
    import onnxruntime  # noqa: F401
except Exception:  # OCR will report itself unavailable later
    pass
