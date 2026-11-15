"""
Junta todas las piezas DXF de cnc/alucobond (BandejaXxx_ACM4_*.dxf y SoportePrincipal_ACM4_*.dxf) en un solo archivo de corte,
acomodadas en planchas de alucobond. Las piezas se separan por la cara que va hacia arriba en la CNC
(las ranuras V se fresan desde arriba): planchas "cara A arriba" (cara de los huevos arriba) y
"cara B arriba" (cara de los huevos abajo). Solo se rotan 90 grados dentro de la plancha, nunca se espejan.

Uso:  python nesting_corte_bandejas.py [carpeta] [ancho_plancha] [alto_plancha]
Salida: Bandejas_ACM4_CORTE.dxf y Bandejas_ACM4_CORTE_vista.svg en la misma carpeta.
Cantidades: una pieza cuyo encabezado dice '- x2' se coloca dos veces.
"""
import os, sys, math, glob, re
TAG = "ACM4"

DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cnc", "alucobond")
SW = float(sys.argv[2]) if len(sys.argv) > 2 else 2440.0     # plancha (mm)
SH = float(sys.argv[3]) if len(sys.argv) > 3 else 1220.0
MARGEN = 15.0     # borde de la plancha sin usar
SEP = 14.0        # separacion entre piezas (fresa + texto)
LAYERS = [("CORTE_EXTERIOR", 7), ("CORTE_INTERIOR", 1), ("RANURA_V", 5), ("TEXTO_NO_CORTAR", 3), ("PLANCHA_NO_CORTAR", 8)]

def read_dxf(path):
    L = [l.rstrip("\r\n") for l in open(path, encoding="utf-8", errors="replace")]
    pairs = [(L[i].strip(), L[i + 1]) for i in range(0, len(L) - 1, 2)]
    polys, lines, texts = [], [], []
    i = 0; ent = False
    while i < len(pairs):
        c, v = pairs[i]
        if c == "2" and v == "ENTITIES": ent = True
        if ent and c == "0" and v == "POLYLINE":
            lay = None; pts = []; i += 1
            while not (pairs[i][0] == "0" and pairs[i][1] == "VERTEX"):
                if pairs[i][0] == "8": lay = pairs[i][1]
                i += 1
            while pairs[i][1] != "SEQEND":
                if pairs[i][0] == "0" and pairs[i][1] == "VERTEX":
                    x = y = None; i += 1
                    while pairs[i][0] != "0":
                        if pairs[i][0] == "10": x = float(pairs[i][1])
                        if pairs[i][0] == "20": y = float(pairs[i][1])
                        i += 1
                    pts.append((x, y)); continue
                i += 1
            polys.append((lay, pts)); continue
        if ent and c == "0" and v == "LINE":
            d = {}; i += 1
            while pairs[i][0] != "0": d[pairs[i][0]] = pairs[i][1]; i += 1
            lines.append((d["8"], (float(d["10"]), float(d["20"])), (float(d["11"]), float(d["21"])))); continue
        if ent and c == "0" and v == "TEXT":
            d = {}; i += 1
            while pairs[i][0] != "0": d[pairs[i][0]] = pairs[i][1]; i += 1
            texts.append((d["8"], (float(d["10"]), float(d["20"])), float(d["40"]), d["1"])); continue
        i += 1
    return polys, lines, texts

piezas = []
for f in sorted(f_ for f_ in glob.glob(os.path.join(DIR, f"Bandeja*_{TAG}_*.dxf")) + glob.glob(os.path.join(DIR, f"SoportePrincipal_{TAG}_*.dxf"))
                if "_CORTE" not in os.path.basename(f_)):
    polys, lines, texts = read_dxf(f)
    nombre = os.path.basename(f)[:-4].replace(f"_{TAG}_", " ")
    cant = max([int(m_.group(1)) for t_ in texts for m_ in [re.search(r"- x(\d+)", t_[3])] if m_] or [1])
    cara = "A" if any("CARA ARRIBA EN CNC: A" in t[3] for t in texts) else "B"
    geo = [p for _, ps in polys for p in ps]
    x0, x1 = min(p[0] for p in geo), max(p[0] for p in geo); y0, y1 = min(p[1] for p in geo), max(p[1] for p in geo)
    # textos: solo los que caen cerca de la pieza (angulos de pliegue); los encabezados se reemplazan por una etiqueta
    keep_t = [t for t in texts if x0 - 5 <= t[1][0] <= x1 + 5 and y0 - 5 <= t[1][1] <= y1 + 6 and "CARA ARRIBA" not in t[3]
              and not t[3].startswith(("PARED ", "PISO ", "Ranura V", "Referencia", "SOPORTE ", "OREJA ", "Borde "))]
    keep_l = [l for l in lines if l[0] == "RANURA_V"]
    for k_ in range(cant):
        piezas.append(dict(nombre=nombre + (f" {k_ + 1}de{cant}" if cant > 1 else ""), cara=cara, polys=polys, lines=keep_l,
                           texts=keep_t, bb=(x0, y0, x1, y1), w=x1 - x0, h=y1 - y0))

def place(group):
    """estantes: piezas ordenadas por alto; se acuestan (lado largo horizontal) si caben"""
    items = []
    for p in group:
        rot = p["h"] > p["w"] and p["h"] <= SW - 2 * MARGEN
        w, h = (p["h"], p["w"]) if rot else (p["w"], p["h"])
        if w > SW - 2 * MARGEN or h > SH - 2 * MARGEN:
            rot = not rot; w, h = h, w
            if w > SW - 2 * MARGEN or h > SH - 2 * MARGEN: raise SystemExit(f"{p['nombre']} no cabe en la plancha {SW}x{SH}")
        items.append(dict(p=p, rot=rot, w=w, h=h + 6))      # +6: etiqueta sobre la pieza
    items.sort(key=lambda it: -it["h"])
    sheets = []
    for it in items:
        ok = False
        for sh in sheets:
            for shelf in sh["shelves"]:
                if it["h"] <= shelf["h"] and shelf["x"] + it["w"] <= SW - MARGEN:
                    it["x"], it["y"] = shelf["x"], shelf["y"]; shelf["x"] += it["w"] + SEP; sh["items"].append(it); ok = True; break
            if ok: break
            if sh["ytop"] + it["h"] <= SH - MARGEN:
                shelf = dict(y=sh["ytop"], h=it["h"], x=MARGEN + it["w"] + SEP)
                it["x"], it["y"] = MARGEN, sh["ytop"]; sh["shelves"].append(shelf); sh["ytop"] += it["h"] + SEP; sh["items"].append(it); ok = True; break
        if not ok:
            sh = dict(shelves=[dict(y=MARGEN, h=it["h"], x=MARGEN + it["w"] + SEP)], ytop=MARGEN + it["h"] + SEP, items=[])
            it["x"], it["y"] = MARGEN, MARGEN; sh["items"].append(it); sheets.append(sh)
    return sheets

def xf(it, p):
    """coordenadas de la pieza -> plancha (rotacion 90 antihoraria si rot)"""
    x0, y0, x1, y1 = it["p"]["bb"]; x, y = p[0] - x0, p[1] - y0
    if it["rot"]: x, y = (y1 - y0) - y, x
    return (it["x"] + x, it["y"] + y)

out_polys, out_lines, out_texts = [], [], []
svg = []; ox = 0.0; resumen = []
for cara, titulo in (("A", "CARA A ARRIBA (cara de los huevos hacia arriba)"), ("B", "CARA B ARRIBA (cara de los huevos hacia abajo)")):
    grupo = [p for p in piezas if p["cara"] == cara]
    for k, sh in enumerate(place(grupo)):
        def T(q, ox=ox): return (q[0] + ox, q[1])
        frame = [(0, 0), (SW, 0), (SW, SH), (0, SH)]
        out_polys.append(("PLANCHA_NO_CORTAR", [T(q) for q in frame]))
        out_texts.append(("TEXTO_NO_CORTAR", T((10, SH + 12)), 18.0, f"PLANCHA {cara}{k + 1} - ACM 4 mm {SW:.0f}x{SH:.0f} - {titulo}"))
        resumen.append((f"{cara}{k + 1}", [it["p"]["nombre"] for it in sh["items"]]))
        for it in sh["items"]:
            p = it["p"]
            for lay, pts in p["polys"]: out_polys.append((lay, [T(xf(it, q)) for q in pts]))
            for lay, a, b in p["lines"]: out_lines.append((lay, T(xf(it, a)), T(xf(it, b))))
            for lay, q, h, txt in p["texts"]: out_texts.append((lay, T(xf(it, q)), h, txt, 90.0 if it["rot"] else 0.0))
            out_texts.append(("TEXTO_NO_CORTAR", T((it["x"], it["y"] + it["h"] - 4.5)), 4.0, f"{p['nombre']} - cara {cara} arriba"))
        ox += SW + 200.0

def f4(v): return "%.4f" % v
o = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
     "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(LAYERS))]
for nm, col in LAYERS: o += ["0", "LAYER", "2", nm, "70", "0", "62", str(col), "6", "CONTINUOUS"]
o += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
for lay, pts in out_polys:
    o += ["0", "POLYLINE", "8", lay, "66", "1", "70", "1", "10", "0", "20", "0", "30", "0"]
    for x, y in pts: o += ["0", "VERTEX", "8", lay, "10", f4(x), "20", f4(y), "30", "0"]
    o += ["0", "SEQEND", "8", lay]
for lay, a, b in out_lines: o += ["0", "LINE", "8", lay, "10", f4(a[0]), "20", f4(a[1]), "30", "0", "11", f4(b[0]), "21", f4(b[1]), "31", "0"]
for t in out_texts:
    lay, q, h, txt = t[:4]; rot = t[4] if len(t) > 4 else 0.0
    o += ["0", "TEXT", "8", lay, "10", f4(q[0]), "20", f4(q[1]), "30", "0", "40", f4(h), "1", txt] + (["50", f4(rot)] if rot else [])
o += ["0", "ENDSEC", "0", "EOF"]
dxf_path = os.path.join(DIR, f"Bandejas_{TAG}_CORTE.dxf")
with open(dxf_path, "w", newline="\r\n", encoding="ascii", errors="replace") as fh: fh.write("\n".join(o) + "\n")

# vista previa SVG
COL = {"CORTE_EXTERIOR": "#111", "CORTE_INTERIOR": "#d22", "RANURA_V": "#1565c0", "TEXTO_NO_CORTAR": "#2e7d32", "PLANCHA_NO_CORTAR": "#999"}
Wt = ox; Ht = SH + 60
Y = lambda y: SH + 40 - y
for lay, pts in out_polys:
    svg.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="%s"/>' % (" ".join("%.1f,%.1f" % (x, Y(y)) for x, y in pts),
               "none" if lay == "PLANCHA_NO_CORTAR" else ("#e9eef3" if lay == "CORTE_EXTERIOR" else "#fff"), COL[lay], "2" if lay == "PLANCHA_NO_CORTAR" else "0.8"))
for lay, a, b in out_lines:
    svg.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="0.8" stroke-dasharray="6,4"/>' % (a[0], Y(a[1]), b[0], Y(b[1]), COL[lay]))
for t in out_texts:
    lay, q, h, txt = t[:4]; rot = t[4] if len(t) > 4 else 0.0
    svg.append('<text x="%.1f" y="%.1f" font-size="%.1f" font-family="sans-serif" fill="%s"%s>%s</text>' % (
        q[0], Y(q[1]), h, COL[lay], (' transform="rotate(%.0f %.1f %.1f)"' % (-rot, q[0], Y(q[1]))) if rot else "", txt))
with open(os.path.join(DIR, f"Bandejas_{TAG}_CORTE_vista.svg"), "w", encoding="utf-8") as fh:
    fh.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f"><rect width="100%%" height="100%%" fill="#fff"/>%s</svg>' % (Wt, Ht, "".join(svg)))

print("piezas:", len(piezas), " cara A:", sum(p["cara"] == "A" for p in piezas), " cara B:", sum(p["cara"] == "B" for p in piezas))
for nm, lst in resumen: print("PLANCHA", nm, ":", ", ".join(lst))
print("->", dxf_path)
