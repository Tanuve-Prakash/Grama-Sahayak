import io
import pytest
from fastapi.testclient import TestClient

from app.orchestrator import Orchestrator
from app.session import SessionStore


@pytest.fixture(scope="session")
def orch():
    return Orchestrator()


@pytest.fixture()
def sessions():
    return SessionStore()


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def make_doc_image(lines, tilt=1.0):
    """Render a synthetic document photo (JPEG bytes) for OCR tests."""
    import glob
    from PIL import Image, ImageDraw, ImageFont
    fonts = glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True) + glob.glob("/usr/share/fonts/**/LiberationSans-Regular.ttf", recursive=True)
    font = ImageFont.truetype(fonts[0], 34) if fonts else ImageFont.load_default()
    im = Image.new("RGB", (1000, 80 + 70 * len(lines)), "white")
    d = ImageDraw.Draw(im)
    for i, l in enumerate(lines):
        d.text((40, 40 + i * 70), l, fill="black", font=font)
    im = im.rotate(tilt, fillcolor="white")
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=70)
    return buf.getvalue()
