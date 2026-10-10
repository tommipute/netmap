"""Immagine di sfondo delle mappe: caricamento, controllo del formato, posizione e trasparenza."""
import struct

import pytest

from app.services import images
from tests.test_api import create

# Bastano le intestazioni: il server legge solo tipo e misure
PNG = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 800, 400) + b"\x08\x06\x00\x00\x00" + b"\x00" * 20
JPEG = (b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
        + b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 300, 600) + b"\x00" * 20)
WEBP_VP8X = b"RIFF" + struct.pack("<I", 100) + b"WEBPVP8X" + struct.pack("<I", 10) + b"\x00" * 4 \
    + (1023).to_bytes(3, "little") + (511).to_bytes(3, "little") + b"\x00" * 20
WEBP_VP8L = b"RIFF" + struct.pack("<I", 100) + b"WEBPVP8L" + struct.pack("<I", 10) + b"\x2f" \
    + ((99) | (49 << 14)).to_bytes(4, "little") + b"\x00" * 20


@pytest.mark.parametrize(("data", "kind", "size"), [
    (PNG, "image/png", (800, 400)),
    (JPEG, "image/jpeg", (600, 300)),
    (WEBP_VP8X, "image/webp", (1024, 512)),
    (WEBP_VP8L, "image/webp", (100, 50)),
])
def test_misure_dall_intestazione(data, kind, size):
    assert images.image_info(data) == (kind, *size)


@pytest.mark.parametrize("data", [
    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    b"GIF89a" + b"\x00" * 20,
    b"",
    PNG[:20],  # troncato
    b"\xff\xd8\xff\xe0" + b"\x00" * 30,  # JPEG senza misure
])
def test_formati_rifiutati(data):
    with pytest.raises(images.ImageError):
        images.image_info(data)


@pytest.fixture()
def network_map(client):
    site = create(client, "/sites", {"name": "Sede"})
    return create(client, "/maps", {"name": "Piano terra", "site_id": site["id"]})


def test_sfondo_della_mappa(client, network_map):
    url = f"/api/maps/{network_map['id']}/background"
    assert client.get(f"/api/maps/{network_map['id']}/view").json()["background"] is None
    assert client.get(url).status_code == 404

    headers = {"Content-Type": "application/octet-stream"}
    saved = client.put(url, params={"x": -100, "y": 50, "width": 1000}, content=PNG, headers=headers)
    assert saved.status_code == 200, saved.text
    bg = saved.json()
    assert (bg["x"], bg["y"], bg["width"], bg["height"], bg["opacity"]) == (-100, 50, 1000, 500, 0.5)
    assert (bg["width_px"], bg["height_px"]) == (800, 400)

    image = client.get(url)
    assert image.content == PNG
    assert image.headers["content-type"] == "image/png"
    assert client.get(f"/api/maps/{network_map['id']}/view").json()["background"] == bg

    # Spostato, ingrandito, più trasparente
    moved = client.patch(url, json={"x": 10, "width": 400, "opacity": 0.3}).json()
    assert (moved["x"], moved["y"], moved["width"], moved["height"], moved["opacity"]) == (10, 50, 400, 200, 0.3)
    assert client.patch(url, json={"opacity": 0}).status_code == 422
    assert client.patch(url, json={"width": 5}).status_code == 422

    # Sostituita senza indicazioni: resta dov'era, con l'altezza della nuova immagine
    replaced = client.put(url, content=JPEG, headers=headers).json()
    assert (replaced["x"], replaced["y"], replaced["width"], replaced["height"]) == (10, 50, 400, 200)
    assert replaced["width_px"] == 600
    assert client.get(url).headers["content-type"] == "image/jpeg"

    # Un SVG no (può contenere codice)
    refused = client.put(url, content=b"<svg xmlns='http://www.w3.org/2000/svg'/>", headers=headers)
    assert refused.status_code == 422
    assert "PNG, JPG o WebP" in refused.json()["detail"]
    assert client.get(url).content == JPEG

    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.patch(url, json={"opacity": 0.5}).status_code == 404


def test_sfondo_troppo_grande_e_mappa_cancellata(client, network_map, monkeypatch):
    url = f"/api/maps/{network_map['id']}/background"
    headers = {"Content-Type": "application/octet-stream"}
    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 100)
    too_big = client.put(url, content=PNG + b"\x00" * 200, headers=headers)
    assert too_big.status_code == 422
    assert "troppo grande" in too_big.json()["detail"]

    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 15 * 1024 * 1024)
    first = client.put(url, content=PNG, headers=headers).json()
    assert first["width"] == 800  # senza indicazioni: la larghezza dell'immagine
    assert client.put("/api/maps/999999/background", content=PNG, headers=headers).status_code == 404

    # Cancellando la mappa sparisce anche lo sfondo
    assert client.delete(f"/api/maps/{network_map['id']}").status_code == 204
    assert client.get(url).status_code == 404
