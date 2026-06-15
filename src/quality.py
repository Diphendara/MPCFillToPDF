import logging
from pathlib import Path

_log = logging.getLogger(__name__)

def evaluate_image_quality_pillow(image_path: Path | str) -> float:
    """
    Evaluates the quality score of an image using Pillow-based Laplacian variance.
    Converts image to grayscale, applies a 3x3 Laplacian kernel, and returns the variance.
    """
    try:
        from PIL import Image, ImageFilter, ImageStat
        with Image.open(image_path) as img:
            img_gray = img.convert("L")
            laplacian_kernel = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0])
            laplacian_img = img_gray.filter(laplacian_kernel)
            stat = ImageStat.Stat(laplacian_img)
            return float(stat.var[0])
    except Exception as e:
        _log.error(f"Error evaluating image quality (Pillow) for {image_path}: {e}")
        return 0.0

def evaluate_image_quality_opencv(image_path: Path | str) -> float:
    """
    Evaluates the quality score of an image using OpenCV-based Laplacian variance.
    Loads image in grayscale, computes double-precision float64 Laplacian, and returns the variance.
    """
    try:
        import cv2
        import numpy as np

        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            _log.error(f"Error loading image via OpenCV: {image_path}")
            return 0.0

        laplacian = cv2.Laplacian(img, cv2.CV_64F)
        variance = laplacian.var()
        return float(variance)
    except Exception as e:
        _log.error(f"Error evaluating image quality (OpenCV) for {image_path}: {e}")
        return 0.0

def evaluate_image_quality(image_path: Path | str, method: str = "pillow") -> float:
    """
    Evaluates the quality score of an image using the selected quality method.
    Default method is "pillow", but can be set to "opencv".
    """
    if method == "opencv":
        return evaluate_image_quality_opencv(image_path)
    else:
        return evaluate_image_quality_pillow(image_path)
