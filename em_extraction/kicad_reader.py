"""KiCad `.kicad_pcb` reader (s-expression, no `pcbnew`).

`pcbnew` exists only in KiCad's bundled Python. Importing it here would break
pytest and `python run_pipeline.py` in the project venv. The board file is
parsed as text instead.

KiCad stores nanometres internally; the `.kicad_pcb` text uses millimetres.
Coordinates and thicknesses in `BoardGeometry` are metres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# `.kicad_pcb` linear unit → metres.
MM_TO_M = 1e-3

POWER_NET = "VCC"
IC_FOOTPRINT_REF = "U1"


@dataclass(frozen=True)
class StackupLayer:
    name: str
    thickness_m: float
    material: str  # "copper" or "dielectric"
    epsilon_r: float | None = None


@dataclass(frozen=True)
class BoardFeature:
    """A pad or via location on the board, in metres, origin = KiCad board origin."""

    x_m: float
    y_m: float
    net: str
    kind: str  # "pad" or "via"
    ref: str = ""  # footprint reference; empty for free vias
    pad: str = ""  # pad number; empty for vias


@dataclass(frozen=True)
class BoardGeometry:
    """Layout-derived PDN features. Produced from a `.kicad_pcb` by `read_board`."""

    stackup: list[StackupLayer] = field(default_factory=list)
    pads_and_vias: list[BoardFeature] = field(default_factory=list)
    ic_power_pin: BoardFeature | None = None
    decap_sites: list[BoardFeature] = field(default_factory=list)
    outline_min_m: tuple[float, float] = (0.0, 0.0)
    outline_max_m: tuple[float, float] = (0.0, 0.0)

    def inner_dielectric(self) -> tuple[float, float]:
        """Thickness (m) and εr of the dielectric between the inner copper pair.

        On a 4-layer board that is In1.Cu ↔ In2.Cu (the PDN cavity). Falls back
        to the first two coppers if there are fewer than four copper layers.
        """
        copper_idx = [i for i, layer in enumerate(self.stackup) if layer.material == "copper"]
        if len(copper_idx) < 2:
            raise ValueError("stackup needs at least two copper layers")
        if len(copper_idx) >= 4:
            i0, i1 = copper_idx[1], copper_idx[2]
        else:
            i0, i1 = copper_idx[0], copper_idx[1]
        dielectrics = self.stackup[i0 + 1 : i1]
        if not dielectrics:
            raise ValueError("no dielectric between the inner copper pair")
        thickness_m = sum(layer.thickness_m for layer in dielectrics)
        eps = next((layer.epsilon_r for layer in dielectrics if layer.epsilon_r is not None), None)
        if eps is None:
            raise ValueError("inner dielectric is missing epsilon_r")
        return thickness_m, float(eps)


def read_board(path: Path | str) -> BoardGeometry:
    """Read via/pad coordinates and stackup from a KiCad 8 `.kicad_pcb` file."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    root = parse_sexpr(text)
    if not _is_form(root, "kicad_pcb"):
        raise ValueError(f"{path} is not a kicad_pcb s-expression")

    stackup = _read_stackup(root)
    net_names = _read_net_map(root)
    pads_and_vias = _read_footprint_pads(root) + _read_vias(root, net_names)
    outline_min_m, outline_max_m = _read_outline(root, pads_and_vias)

    ic_power_pin = next(
        (
            feat
            for feat in pads_and_vias
            if feat.kind == "pad" and feat.ref == IC_FOOTPRINT_REF and feat.net == POWER_NET
        ),
        None,
    )
    decap_sites = [feat for feat in pads_and_vias if feat.kind == "via" and feat.net == POWER_NET]
    return BoardGeometry(
        stackup=stackup,
        pads_and_vias=pads_and_vias,
        ic_power_pin=ic_power_pin,
        decap_sites=decap_sites,
        outline_min_m=outline_min_m,
        outline_max_m=outline_max_m,
    )


# --- s-expression ----------------------------------------------------------

def parse_sexpr(text: str) -> Any:
    """Parse a KiCad s-expression into nested Python lists / atoms."""
    tokens = _tokenize(text)
    if not tokens:
        raise ValueError("empty s-expression")
    value, index = _parse_tokens(tokens, 0)
    if index != len(tokens):
        raise ValueError("trailing tokens after top-level s-expression")
    return value


def _tokenize(text: str) -> list[str | tuple[str, str]]:
    tokens: list[str | tuple[str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == ";":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch in "()":
            tokens.append(ch)
            i += 1
            continue
        if ch == '"':
            i += 1
            chars: list[str] = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    chars.append(text[i + 1])
                    i += 2
                    continue
                chars.append(text[i])
                i += 1
            if i >= n:
                raise ValueError("unterminated string in s-expression")
            i += 1
            tokens.append(("str", "".join(chars)))
            continue
        j = i
        while j < n and (not text[j].isspace()) and text[j] not in "();\"":
            j += 1
        tokens.append(("atom", text[i:j]))
        i = j
    return tokens


def _parse_tokens(tokens: list[str | tuple[str, str]], index: int) -> tuple[Any, int]:
    if index >= len(tokens):
        raise ValueError("unexpected end of s-expression")
    tok = tokens[index]
    if tok == "(":
        items: list[Any] = []
        index += 1
        while index < len(tokens) and tokens[index] != ")":
            item, index = _parse_tokens(tokens, index)
            items.append(item)
        if index >= len(tokens):
            raise ValueError("unterminated list in s-expression")
        return items, index + 1
    if tok == ")":
        raise ValueError("unexpected ')' in s-expression")
    kind, value = tok  # type: ignore[misc]
    if kind == "str":
        return value, index + 1
    return _atom_value(value), index + 1


def _atom_value(raw: str) -> Any:
    if raw in {"yes", "true"}:
        return True
    if raw in {"no", "false"}:
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _is_form(node: Any, name: str) -> bool:
    return isinstance(node, list) and node and node[0] == name


def _children(node: list[Any], name: str) -> list[list[Any]]:
    return [item for item in node[1:] if _is_form(item, name)]


def _child(node: list[Any], name: str) -> list[Any] | None:
    for item in node[1:]:
        if _is_form(item, name):
            return item
    return None


def _arg(node: list[Any], name: str, default: Any = None) -> Any:
    child = _child(node, name)
    if child is None or len(child) < 2:
        return default
    return child[1]


# --- board sections --------------------------------------------------------

def _read_stackup(root: list[Any]) -> list[StackupLayer]:
    setup = _child(root, "setup")
    if setup is None:
        raise ValueError("kicad_pcb is missing (setup ...)")
    stackup = _child(setup, "stackup")
    if stackup is None:
        raise ValueError("kicad_pcb setup is missing (stackup ...)")
    layers: list[StackupLayer] = []
    for layer in _children(stackup, "layer"):
        if len(layer) < 2 or not isinstance(layer[1], str):
            continue
        name = layer[1]
        type_name = str(_arg(layer, "type", "")).lower()
        thickness_mm = float(_arg(layer, "thickness", 0.0) or 0.0)
        if type_name == "copper":
            material = "copper"
            epsilon_r = None
        elif "mask" in type_name or "paste" in type_name or "silk" in type_name:
            continue
        else:
            material = "dielectric"
            eps = _arg(layer, "epsilon_r")
            epsilon_r = float(eps) if eps is not None else None
        layers.append(
            StackupLayer(
                name=name,
                thickness_m=thickness_mm * MM_TO_M,
                material=material,
                epsilon_r=epsilon_r,
            )
        )
    if not layers:
        raise ValueError("stackup has no copper or dielectric layers")
    return layers


def _read_net_map(root: list[Any]) -> dict[int, str]:
    nets: dict[int, str] = {}
    for net in _children(root, "net"):
        if len(net) < 2:
            continue
        net_id = int(net[1])
        name = str(net[2]) if len(net) > 2 else ""
        nets[net_id] = name
    return nets


def _read_footprint_pads(root: list[Any]) -> list[BoardFeature]:
    features: list[BoardFeature] = []
    for fp in _children(root, "footprint"):
        fx, fy, rot = _xy_rot(fp)
        ref = _footprint_reference(fp)
        for pad in _children(fp, "pad"):
            px, py, _prot = _xy_rot(pad)
            ax, ay = _rotate(px, py, rot)
            net = _pad_net_name(pad)
            pad_num = str(pad[1]) if len(pad) > 1 else ""
            features.append(
                BoardFeature(
                    x_m=(fx + ax) * MM_TO_M,
                    y_m=(fy + ay) * MM_TO_M,
                    net=net,
                    kind="pad",
                    ref=ref,
                    pad=pad_num,
                )
            )
    return features


def _read_vias(root: list[Any], net_names: dict[int, str]) -> list[BoardFeature]:
    features: list[BoardFeature] = []
    for via in _children(root, "via"):
        x, y, _rot = _xy_rot(via)
        net_form = _child(via, "net")
        net = ""
        if net_form is not None and len(net_form) >= 2:
            net_id = int(net_form[1])
            net = net_names.get(net_id, str(net_id))
            if len(net_form) >= 3:
                net = str(net_form[2])
        features.append(
            BoardFeature(
                x_m=x * MM_TO_M,
                y_m=y * MM_TO_M,
                net=net,
                kind="via",
            )
        )
    return features


def _read_outline(
    root: list[Any],
    pads_and_vias: list[BoardFeature],
) -> tuple[tuple[float, float], tuple[float, float]]:
    xs: list[float] = []
    ys: list[float] = []
    for item in root[1:]:
        if not isinstance(item, list):
            continue
        if _graphic_layer(item) != "Edge.Cuts":
            continue
        for x_mm, y_mm in _graphic_points_mm(item):
            xs.append(x_mm * MM_TO_M)
            ys.append(y_mm * MM_TO_M)
    if not xs:
        if not pads_and_vias:
            raise ValueError("board has no Edge.Cuts outline and no pads/vias")
        xs = [feat.x_m for feat in pads_and_vias]
        ys = [feat.y_m for feat in pads_and_vias]
        margin = 2e-3
        return (min(xs) - margin, min(ys) - margin), (max(xs) + margin, max(ys) + margin)
    return (min(xs), min(ys)), (max(xs), max(ys))


def _graphic_layer(item: list[Any]) -> str | None:
    layer = _child(item, "layer")
    if layer is not None and len(layer) >= 2:
        return str(layer[1])
    return None


def _graphic_points_mm(item: list[Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    start = _child(item, "start")
    end = _child(item, "end")
    if start is not None and len(start) >= 3:
        points.append((float(start[1]), float(start[2])))
    if end is not None and len(end) >= 3:
        points.append((float(end[1]), float(end[2])))
    xy = _child(item, "xy")
    if xy is not None and len(xy) >= 3:
        points.append((float(xy[1]), float(xy[2])))
    for child in item[1:]:
        if isinstance(child, list) and child and child[0] in {"pts", "polygon", "filled_polygon"}:
            points.extend(_graphic_points_mm(child))
        elif _is_form(child, "xy") and len(child) >= 3:
            points.append((float(child[1]), float(child[2])))
    return points


def _footprint_reference(fp: list[Any]) -> str:
    for prop in _children(fp, "property"):
        if len(prop) >= 3 and prop[1] == "Reference":
            return str(prop[2])
    for text in _children(fp, "fp_text"):
        if len(text) >= 3 and text[1] == "reference":
            return str(text[2])
    return ""


def _pad_net_name(pad: list[Any]) -> str:
    net = _child(pad, "net")
    if net is None or len(net) < 2:
        return ""
    if len(net) >= 3:
        return str(net[2])
    return str(net[1])


def _xy_rot(node: list[Any]) -> tuple[float, float, float]:
    at = _child(node, "at")
    if at is None or len(at) < 3:
        return 0.0, 0.0, 0.0
    rot = float(at[3]) if len(at) > 3 and isinstance(at[3], (int, float)) else 0.0
    return float(at[1]), float(at[2]), rot


def _rotate(x: float, y: float, rot_deg: float) -> tuple[float, float]:
    if rot_deg == 0:
        return x, y
    rad = math.radians(rot_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return x * cos_a - y * sin_a, x * sin_a + y * cos_a
