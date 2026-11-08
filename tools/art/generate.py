#!/usr/bin/env python3
"""Compile editable palette/character grids into deterministic pixel SVGs.

Python 3 standard library only. Run from any directory; --check never writes.
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
GRIDS = Path(__file__).resolve().parent / 'grids'
ZONES = ('lobby', 'mine', 'shiba', 'building', 'sea', 'end')
SIZES = {
    'player': (256, 32), 'coin': (48, 12),
    **{f'bg_{zone}': (480, 270) for zone in ZONES},
    **{f'tile_{zone}': (32, 16) for zone in ZONES},
    'about_board': (72, 72), 'arcade': (32, 56), 'sign': (48, 40),
    'mine_office': (96, 80), 'lantern': (12, 20), 'minecart': (56, 16),
    'debt_board': (72, 40), 'jeep': (96, 56), 'cone': (12, 16),
    'building_site': (96, 80), 'crane': (64, 128), 'sea_house': (96, 80),
    'raft': (56, 12), 'sofa': (40, 24), 'mailbox': (32, 48),
    'flag': (32, 64), 'portal': (48, 64),
}


def read_grid(name):
    data = json.loads((GRIDS / f'{name}.json').read_text())
    w, h = SIZES[name]
    if (data['width'], data['height']) != (w, h):
        raise ValueError(f'{name}: size must be {w}x{h}')
    rows, palette = data['rows'], data['palette']
    if len(rows) != h or any(len(row) != w for row in rows):
        raise ValueError(f'{name}: incorrect grid dimensions')
    if any(len(k) != 1 or k == '.' or not re.fullmatch(r'#[0-9a-f]{6}', v)
           for k, v in palette.items()):
        raise ValueError(f'{name}: invalid palette (dot is reserved for transparency)')
    if set(''.join(rows)) - set(palette) - {'.'}:
        raise ValueError(f'{name}: unknown palette symbol')
    if name.startswith('bg_'):
        if '.' in ''.join(rows) or any(row[0] != row[-1] for row in rows):
            raise ValueError(f'{name}: background must be opaque and seamless')
    elif name.startswith('tile_'):
        if any(row[0] != row[15] or row[16] != row[31] for row in rows):
            raise ValueError(f'{name}: horizontal tile seam')
        if rows[0][16:] != rows[-1][16:]:
            raise ValueError(f'{name}: vertical fill tile seam')
    else:
        if '.' not in ''.join(rows) or set(rows[-1]) == {'.'}:
            raise ValueError(f'{name}: transparent margins and grounded feet required')
    if name in ('player', 'coin'):
        fw, count = (32, 8) if name == 'player' else (12, 4)
        frames = [tuple(row[i*fw:(i+1)*fw] for row in rows) for i in range(count)]
        if len(set(frames)) != count:
            raise ValueError(f'{name}: animation frames must be distinct')
        if any(set(frame[-1]) == {'.'} for frame in frames):
            raise ValueError(f'{name}: frame has empty bottom row')
    return data


def rectangles(rows):
    """Merge horizontal runs, then stack identical runs on consecutive rows.

    Rectangles never overlap or cross transparent pixels. Merging vertical
    runs keeps large opaque backgrounds under the 50 KB asset budget.
    """
    active, result = {}, []
    for y, row in enumerate(rows):
        runs = {}
        x = 0
        while x < len(row):
            end = x + 1
            while end < len(row) and row[end] == row[x]:
                end += 1
            if row[x] != '.':
                key = (x, end-x, row[x])
                rect = active.pop(key, [x, y, end-x, 0, row[x]])
                rect[3] += 1
                runs[key] = rect
            x = end
        result.extend(active.values())
        active = runs
    result.extend(active.values())
    return sorted(result, key=lambda r: (r[1], r[0]))


def compile_svg(data):
    w, h, palette = data['width'], data['height'], data['palette']
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
             f'viewBox="0 0 {w} {h}" shape-rendering="crispEdges">']
    rects = rectangles(data['rows'])
    for code, color in sorted(palette.items()):
        lines.append(f'<g fill="{color}">')
        for x, y, rw, rh, symbol in rects:
            if symbol == code:
                lines.append(f'<rect x="{x}" y="{y}" width="{rw}" height="{rh}"/>')
        lines.append('</g>')
    lines.append('</svg>')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='validate grids and require SVGs to match')
    args = parser.parse_args()
    actual = {p.stem for p in GRIDS.glob('*.json')}
    if actual != set(SIZES):
        raise ValueError(f'Grid inventory mismatch: {actual ^ set(SIZES)}')
    sizes = []
    for name in SIZES:
        svg = compile_svg(read_grid(name))
        size = len(svg.encode())
        if size >= 50_000:
            raise ValueError(f'{name}: {size} bytes exceeds 50 KB budget')
        dest = ROOT / 'assets' / f'{name}.svg'
        if args.check:
            if not dest.exists() or dest.read_text() != svg:
                raise ValueError(f'{name}: SVG is missing or stale; run generate.py')
        else:
            dest.write_text(svg)
        sizes.append((size, name))
    size, name = max(sizes)
    print(f'{"Checked" if args.check else "Generated"} {len(sizes)} SVGs; largest: {name} ({size:,} bytes)')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as exc:
        sys.exit(str(exc))
