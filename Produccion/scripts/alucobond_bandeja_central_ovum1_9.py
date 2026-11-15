"""
Ovum1_9: BandejaCentral en alucobond (ACM) de 5 mm para corte CNC, con ranurado en V y plegado.

La superficie por donde ruedan los huevos (la del modelo BandejaCentral) no cambia: el material crece hacia
afuera (abajo del piso y por fuera de las paredes).

Piezas:
  Piso           1 pieza, 4 pliegues transversales. Todas las ranuras por la cara inferior (B): la cara de
                 los huevos queda con la piel de aluminio continua. 1 pliegue es normal (cierra la V) y 3 son
                 "invertidos" (pocos grados, la V abre; se rellena con adhesivo).
  Embudo_Izq/Der paredes del embudo delantero; ranuras por fuera (cara B), piel continua por dentro.
  Pared_U        lados rectos + punta trasera; ranuras por dentro (cara A).
Las paredes se cortan en las esquinas a 144 grados (v1/v4): ahi la union queda cerrada por dentro.
El piso lleva pestanas que atraviesan ranuras de las paredes: la posicion de las paredes y los angulos
de los pliegues del piso quedan definidos por el corte CNC, no por la mano.

Salida: DXF 1:1 en mm por pieza (vistos desde la cara que va hacia arriba en la CNC), SVG de vista previa,
y los solidos 3D en la coleccion Alucobond_BandejaCentral.
Uso:  blender --background Ovum1_9.blend --python alucobond_bandeja_central_ovum1_9.py -- out <dir> [save]
"""
import bpy, bmesh, json, sys, math, os
from mathutils import Vector, Matrix
from mathutils.geometry import tessellate_polygon
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("out") + 1] if "out" in argv else os.path.join(os.path.dirname(bpy.data.filepath), "cnc", "alucobond")
os.makedirs(OUT, exist_ok=True)

# ------------------------------------------------------------------ parametros (mm)
T = 5.0          # espesor del panel
C_PISO = 0.15    # holgura borde del piso - cara interior de la pared
C_SLOT = 0.15    # holgura pestana - ranura (por lado)
W_TAB = 15.0     # ancho de pestana
R_TOOL = 1.6     # radio de la fresa de corte (1/8" = 3.175 mm) -> alivios "dogbone"
M_BAJO = 0.0     # la pared termina al ras de la cara inferior del piso (nada cuelga bajo las bandejas):
                 # las pestanas del piso entran en muescas abiertas por abajo
# remaches ciegos de aluminio D4 cabeza redonda; escuadras de aluminio de 2 mm POR FUERA, en cada pestana:
# un ala bajo el piso (al nivel de su cara inferior) y la otra subiendo por la cara exterior de la pared
R_HOLE = 2.05    # agujero D4.1
CLIP_H = 20.0    # ala bajo el piso, medida desde la cara exterior de la pared
CLIP_V = 18.0    # ala exterior, medida desde la cara inferior del piso
CLIP_T = 2.0
RIV_PISO = 8.0   # remache del piso: a 8 mm de la cara interior de la pared (zona donde un huevo no llega)
RIV_PARED = 6.0  # remache de la pared: 6 mm sobre la cara superior del piso (cabeza por dentro)
TAB_MIN_SEG = 35.0
RESTO = 0.8      # material que queda en el fondo de la ranura en V (piel 0.5 + 0.3 de nucleo)

O = bpy.data.objects
src = O["BandejaCentral"]
V = [(src.matrix_world @ v.co) * 1000.0 for v in src.data.vertices]
ZTOP = V[2].z
rep = {"avisos": []}

def v2(p): return Vector((p.x, p.y))
def norm2(v): return v / v.length

# ------------------------------------------------------------------ travesano que apoya el piso
def travesano():
    """caja(s) del travesano bajo las bandejas superiores: caras de aluminio anchas en x sobre z 0.115"""
    J = O.get("Bastidor_Largueros_2020.003")
    if not J: return None
    bm = bmesh.new(); bm.from_mesh(J.data); bm.transform(J.matrix_world)
    ws = [f for f in bm.faces if max(v.co.x for v in f.verts) - min(v.co.x for v in f.verts) > 0.15 and min(v.co.z for v in f.verts) > 0.115]
    vv = {v for f in ws for v in f.verts}
    out = [1000 * f_(v.co[i] for v in vv) for i in range(3) for f_ in (min, max)] if vv else None
    bm.free(); return out
TRAV = travesano()
NOTCH = 1.0       # holgura de la muesca de la pared sobre el travesano (por lado, en y)

# ------------------------------------------------------------------ piso: perfil (y, z) de atras hacia adelante
# se omite el pliegue de 0.4 grados en y=42.78 (caras 21 y 3 casi coplanares, desvio 0.03 mm)
PROF = [V[27], V[1], V[0], V[20], V[12], V[7]]
panels = []; U = 0.0
for a, b in zip(PROF[:-1], PROF[1:]):
    A = Vector((0, a.y, a.z)); B = Vector((0, b.y, b.z)); L = (B - A).length; t = (B - A) / L
    panels.append(dict(ya=a.y, za=a.z, yb=b.y, zb=b.z, L=L, t=t, n=Vector((0, t.z, -t.y)), U0=U))
    U += L
U_END = U
def panel_of_y(y):
    for j, p in enumerate(panels):
        if p["yb"] - 1e-6 <= y <= p["ya"] + 1e-6: return j
    return 0 if y > panels[0]["ya"] else len(panels) - 1
def u_of(y):
    p = panels[panel_of_y(y)]; return p["U0"] + (p["ya"] - y) / (p["ya"] - p["yb"]) * p["L"]
def panel_of_u(u):
    for j, p in enumerate(panels):
        if p["U0"] - 1e-6 <= u <= p["U0"] + p["L"] + 1e-6: return j
    return len(panels) - 1
def floor3d(x, u, j=None):
    j = panel_of_u(u) if j is None else j; p = panels[j]
    return Vector((x, p["ya"], p["za"])) + (u - p["U0"]) * p["t"]

folds = []
for j in range(len(panels) - 1):
    t0, t1, n0 = panels[j]["t"], panels[j + 1]["t"], panels[j]["n"]
    ang = math.degrees(t0.angle(t1)); valle = t1.dot(n0) > 0
    folds.append(dict(u=panels[j + 1]["U0"], y=panels[j + 1]["ya"], ang=ang, tipo="invertido" if valle else "normal"))

# ------------------------------------------------------------------ paredes
plan_poly = [v2(p) for p in [V[7], V[12], V[20], V[0], V[1], V[22], V[27], V[28], V[4], V[3], V[24], V[13], V[6]]]
def inside2(pt, poly):
    c = False; n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a.y > pt.y) != (b.y > pt.y) and pt.x < (b.x - a.x) * (pt.y - a.y) / (b.y - a.y) + a.x: c = not c
    return c

PIEZAS = [  # nombre, puntos de la cadena (al nivel del piso), cara ranurada / arriba en CNC
    ("Embudo_Izq", [V[7], V[12], V[20], V[0], V[1]], "B"),
    ("Pared_U",    [V[1], V[22], V[27], V[28], V[4]], "A"),
    ("Embudo_Der", [V[6], V[13], V[24], V[3], V[4]], "B"),
]
pieces = []
for name, pts, cara in PIEZAS:
    segs = []
    for i in range(len(pts) - 1):
        C0, C1 = pts[i].copy(), pts[i + 1].copy()
        d = norm2(v2(C1) - v2(C0)); n = Vector((d.y, -d.x))
        mid = (v2(C0) + v2(C1)) / 2
        if inside2(mid + n * 1.0, plan_poly): n = -n
        segs.append(dict(C0=C0, C1=C1, d=d, n=n, L=(v2(C1) - v2(C0)).length, j=panel_of_y((C0.y + C1.y) / 2), a0=0.0, a1=0.0))
    corners = []
    for i in range(len(segs) - 1):
        s0, s1 = segs[i], segs[i + 1]
        th = math.degrees(math.acos(max(-1, min(1, s0["d"].dot(s1["d"])))))
        concava = s1["d"].dot(s0["n"]) < 0          # angulo interior < 180 (como esquina de caja)
        want = (cara == "A")                        # ranura por dentro solo en esquinas concavas
        if concava != want: rep["avisos"].append(f"{name}: esquina {i+1} no coincide con la cara de ranurado")
        if cara == "A":                             # piel por fuera: el desarrollo se mide en la cara exterior
            a = T * math.tan(math.radians(th / 2)); s0["a1"] = a; s1["a0"] = a
        corners.append(dict(i=i + 1, ang=th, concava=concava))
    S = 0.0
    for s in segs:
        s["S"] = S; s["flat"] = s["L"] + s["a0"] + s["a1"]; S += s["flat"]
    # vista: (s, z) es la vista desde dentro si d . (n_out x z) > 0
    s0 = segs[0]; right = Vector((s0["n"].y * 1 - 0, 0 - s0["n"].x * 1))   # n_out x z_up (2D)
    vista_dentro = s0["d"].dot(right) > 0
    mirror = vista_dentro if cara == "B" else not vista_dentro
    pieces.append(dict(name=name, segs=segs, corners=corners, cara=cara, S=S, mirror=mirror, slots=[]))

def s_of(seg, P):
    return seg["S"] + seg["a0"] + (v2(P) - v2(seg["C0"])).dot(seg["d"])

# ------------------------------------------------------------------ geometria 2D
def line_x(p1, d1, p2, d2):
    den = d1.x * d2.y - d1.y * d2.x
    if abs(den) < 1e-12: return None
    t = ((p2.x - p1.x) * d2.y - (p2.y - p1.y) * d2.x) / den
    return p1 + d1 * t
def area2(poly):
    return 0.5 * sum(poly[i].x * poly[(i + 1) % len(poly)].y - poly[(i + 1) % len(poly)].x * poly[i].y for i in range(len(poly)))
def ccw(poly): return poly if area2(poly) > 0 else list(reversed(poly))
def hull(pts):
    P = sorted({(round(p.x, 3), round(p.y, 3)) for p in pts})
    if len(P) < 3: return [Vector(p) for p in P]
    def cr(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 1e-9: lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 1e-9: up.pop()
        up.append(p)
    return [Vector(p) for p in lo[:-1] + up[:-1]]
def offset_convex(poly, c):
    poly = ccw(poly); n = len(poly); L = []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]; d = norm2(b - a); L.append((a + Vector((d.y, -d.x)) * c, d))
    return [line_x(L[i - 1][0], L[i - 1][1], L[i][0], L[i][1]) for i in range(n)]
def dogbone(poly, hole, r=R_TOOL, min_turn=30.0, seg=8):
    """alivios en las esquinas interiores para la fresa (poly en CCW). hole=True: esquinas convexas;
    hole=False (contorno): esquinas entrantes"""
    poly = ccw(poly); n = len(poly); out = []
    for i in range(n):
        A, P, B = poly[i - 1], poly[i], poly[(i + 1) % n]
        if (P - A).length < 1e-6 or (B - P).length < 1e-6: out.append(P); continue
        a, b = norm2(P - A), norm2(B - P); cr = a.x * b.y - a.y * b.x
        turn = math.degrees(math.acos(max(-1, min(1, a.dot(b)))))
        if turn < min_turn or (cr > 0) != hole: out.append(P); continue
        o = norm2(b - a); c = P + o * r
        E1 = P + a * (2 * r * a.dot(o)); E2 = P + b * (2 * r * b.dot(o))
        t1 = math.atan2(E1.y - c.y, E1.x - c.x); tp = math.atan2(P.y - c.y, P.x - c.x); t2 = math.atan2(E2.y - c.y, E2.x - c.x)
        def norm_a(x): return (x + 2 * math.pi) % (2 * math.pi)
        span = norm_a(t2 - t1); via = norm_a(tp - t1)
        if via > span: span = span - 2 * math.pi       # ir por el otro lado, pasando por P
        out.append(E1)
        for k in range(1, seg):
            tt = t1 + span * k / seg; out.append(c + Vector((math.cos(tt), math.sin(tt))) * r)
        out.append(E2)
    return out

# ------------------------------------------------------------------ muescas: lo que pasa bajo las paredes
IGNORAR = ("ACM_", "BandejaCentral", "BandejaLTop", "BandejaRTop", "Huevo")   # laterales: pared compartida (luego)
_dg = bpy.context.evaluated_depsgraph_get(); _sc = bpy.context.scene
def floor_bottom_at(seg, P2):
    p = panels[seg["j"]]
    z_top = p["za"] + (p["ya"] - P2.y) / (p["ya"] - p["yb"]) * (p["zb"] - p["za"]) if abs(p["ya"] - p["yb"]) > 1e-9 else p["za"]
    return z_top - T / abs(p["t"].y)
def blocked(P2, z0, depth):
    org = Vector((P2.x / 1000, P2.y / 1000, z0 / 1000)); left = depth / 1000
    for _ in range(12):
        ok, loc, n, i, ob, m = _sc.ray_cast(_dg, org, Vector((0, 0, -1)), distance=left)
        if not ok: return None
        if not ob.name.startswith(IGNORAR): return ob.name
        left -= (org.z - loc.z) + 0.0002; org = loc + Vector((0, 0, -0.0002))
        if left <= 0: return None
    return None
for pc in pieces:
    for seg in pc["segs"]:
        seg["notch"] = []; cur = None; k = 0; step = 0.5
        while k * step <= seg["L"]:
            p = k * step; P2 = v2(seg["C0"]) + seg["d"] * p; zf = floor_bottom_at(seg, P2)
            hit = None
            # bajo la pared y bajo el ala de la escuadra (afuera 2 mm, adentro hasta CLIP_H)
            DEP = max(M_BAJO, CLIP_T + 0.5) + 0.3
            for t in (0.25, 2.5, 4.75, T + 1.0, T + CLIP_T, -2.0, -6.0, -10.0, -(CLIP_H - T)):
                Pt = P2 + seg["n"] * t
                hit = hit or blocked(Pt, floor_bottom_at(seg, Pt) - 0.05, DEP)
            zz = zf - DEP                       # rayos horizontales hacia afuera: atrapan paredes delgadas y
            while not hit and zz < zf + CLIP_V:  # lo que choque con el ala exterior de la escuadra
                org = Vector((P2.x / 1000, P2.y / 1000, zz / 1000)); d3 = Vector((seg["n"].x, seg["n"].y, 0))
                left = (T + CLIP_T + 0.5) / 1000
                for _ in range(6):
                    ok, loc, n_, i_, ob, m_ = _sc.ray_cast(_dg, org, d3, distance=left)
                    if not ok: break
                    if not ob.name.startswith(IGNORAR): hit = ob.name; break
                    left -= (loc - org).length + 0.0002; org = loc + d3 * 0.0002
                    if left <= 0: break
                zz += 0.7
            if hit:
                if cur is None: cur = [p, p, hit]
                cur[1] = p
            elif cur is not None:
                seg["notch"].append(cur); cur = None
            k += 1
        if cur is not None: seg["notch"].append(cur)
        seg["notch"] = [[max(0.0, a - step - NOTCH), min(seg["L"], b + step + NOTCH), o] for a, b, o in seg["notch"]]

# ------------------------------------------------------------------ piso: contorno con pestanas
loop = []   # (seg, sentido)
for pc in pieces:
    if pc["name"] == "Embudo_Der": loop += [(s, -1) for s in reversed(pc["segs"])]
    else: loop += [(s, 1) for s in pc["segs"]]
def F(P): return Vector((P.x, u_of(P.y)))
flat_raw = [F(s["C0"] if sd > 0 else s["C1"]) for s, sd in loop]
flat_raw.append(F(loop[-1][0]["C0"]))      # v6: cierra el contorno por el borde delantero
lines = []; tabs_all = []; CLIPS = []
for s, sd in loop:
    A3, B3 = (s["C0"], s["C1"]) if sd > 0 else (s["C1"], s["C0"])
    Af, Bf = F(A3), F(B3); df = norm2(Bf - Af)
    inward = Vector((-df.y, df.x))
    if not inside2((Af + Bf) / 2 + inward * 0.5, flat_raw): inward = -inward
    pan = panels[s["j"]]; nf = pan["n"]
    e3 = (s["C1"] - s["C0"]).normalized()
    nw = Vector((s["n"].x, s["n"].y, 0.0))
    u3 = e3.cross(nf)
    if u3.dot(nw) < 0: u3 = -u3
    un = u3.dot(nw)
    e_off = max(C_PISO, C_PISO - T * nf.dot(nw)) / un
    lend = (T - max(0.0, -T * nf.dot(nw)) - 0.1) / un   # la pestana no sobresale de la cara exterior (ahi va la escuadra)
    s["floor"] = dict(e_off=e_off, lend=lend)
    p0 = Af + inward * e_off
    tabs = []
    if s["L"] >= TAB_MIN_SEG:
        nt = max(1, round(s["L"] / 75.0))
        for k in range(nt):
            p = s["L"] * (k + 0.5) / nt
            for na, nb, _o in s["notch"]:
                lo_p, hi_p = na - W_TAB / 2 - 4.0, nb + W_TAB / 2 + 4.0
                if lo_p < p < hi_p:
                    cand = [c for c in (lo_p, hi_p) if W_TAB / 2 + 8 <= c <= s["L"] - W_TAB / 2 - 8]
                    if cand: p = min(cand, key=lambda c: abs(c - p))
                    else: rep["avisos"].append(f"pestana sin lugar fuera de la muesca ({_o})")
            J3 = s["C0"] + e3 * (p * (s["C1"] - s["C0"]).length / s["L"]) if False else s["C0"] + (s["C1"] - s["C0"]) * (p / s["L"])
            Jf = F(J3) if False else None
            # punto plano: sobre la linea del borde, a la misma distancia desde el inicio del lado
            pf = (s["C0"] if sd > 0 else s["C1"])
            dist = (J3 - pf).length
            Jin = p0 + df * dist
            A_ = Jin - df * (W_TAB / 2); D_ = Jin + df * (W_TAB / 2)
            B_ = A_ - inward * (e_off + lend); C_ = D_ - inward * (e_off + lend)
            tabs.append((dist, [A_, B_, C_, D_]))
            # ranura en la pared: (pestana) interseccion (espesor de pared), proyectada a la pared
            planes = [(nf, nf.dot(J3)), (-nf, -(nf.dot(J3) - T)),
                      (e3, e3.dot(J3) + W_TAB / 2), (-e3, -(e3.dot(J3) - W_TAB / 2)),
                      (u3, u3.dot(J3) + lend), (-u3, -(u3.dot(J3) - e_off - 2.0)),
                      (nw, nw.dot(J3) + T), (-nw, -nw.dot(J3))]
            vs = []
            for i1 in range(8):
                for i2 in range(i1 + 1, 8):
                    for i3 in range(i2 + 1, 8):
                        Mx = Matrix((planes[i1][0], planes[i2][0], planes[i3][0]))
                        if abs(Mx.determinant()) < 1e-9: continue
                        X = Mx.inverted() @ Vector((planes[i1][1], planes[i2][1], planes[i3][1]))
                        if all(pn.dot(X) <= pd + 1e-4 for pn, pd in planes): vs.append(X)
            pc_ = next(pc for pc in pieces if s in pc["segs"])
            if M_BAJO > 0:
                slot = hull([Vector((s_of(s, X), X.z)) for X in vs])
                slot = dogbone(offset_convex(slot, C_SLOT), hole=True)
                pc_["slots"].append(slot)
            else:
                # muesca abierta por abajo: rectangulo alineado con la linea del piso en la vista de la pared
                f2 = norm2(Vector((s["L"], s["C1"].z - s["C0"].z)))
                dz_out = -T * nf.dot(nw) / nf.z              # cara superior del piso en la cara exterior de la pared
                pc_.setdefault("muescas_pest", []).append(dict(J=Vector((s_of(s, J3), J3.z)), f=f2,
                                                               hw=W_TAB / 2 + C_SLOT, top=C_SLOT + max(0.0, dz_out) * f2.x))
            tabs_all.append(dict(pieza=pc_["name"], s_centro=round(s_of(s, J3), 2), z=round(J3.z, 2)))
            Jjun = Jin - inward * e_off                       # punto de la junta en el plano del piso
            zdn = Vector((0, 0, -1)); wdn = (zdn - e3 * zdn.dot(e3)).normalized()
            ang = math.degrees(math.acos(max(-1, min(1, u3.dot(wdn)))))   # cara inferior del piso / cara exterior de la pared
            Jb = J3 - Vector((0, 0, T / nf.z))
            Jbo = Jb + nw * T + Vector((0, 0, -T * nf.dot(nw) / nf.z))   # arista exterior-inferior (plano inferior del piso)
            CLIPS.append(dict(pieza=pc_["name"], s=s_of(s, J3), z_rem=J3.z + RIV_PARED,
                              hole_piso=Jjun + inward * RIV_PISO, ang=ang, Jb=Jb, Jbo=Jbo, e3=e3, u3=u3, nf=nf, nw=nw, wdn=wdn))
    lines.append(dict(p=p0, d=df, tabs=tabs, sd=sd, s=s))
# borde delantero libre (u = U_END)
lines.append(dict(p=Vector((0, U_END)), d=Vector((-1, 0)), tabs=[], sd=0, s=None))
corners_f = [line_x(lines[i - 1]["p"], lines[i - 1]["d"], lines[i]["p"], lines[i]["d"]) for i in range(len(lines))]
floor_poly = []
for i, ln in enumerate(lines):
    floor_poly.append(corners_f[i])
    for dist, quad in sorted(ln["tabs"], key=lambda q: q[0]): floor_poly += quad
floor_poly = dogbone(floor_poly, hole=False, min_turn=45.0)
def circ(c, r=R_HOLE, n=24):
    return [c + Vector((math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n))) * r for k in range(n)]
FLOOR_HOLES = [circ(c["hole_piso"]) for c in CLIPS]
for pc in pieces: pc["holes"] = [circ(Vector((c["s"], c["z_rem"]))) for c in CLIPS if c["pieza"] == pc["name"]]

def x_range_at_u(poly, u):
    u += 1e-5; xs = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        if (a.y - u) * (b.y - u) < 0: xs.append(a.x + (u - a.y) / (b.y - a.y) * (b.x - a.x))
    return min(xs), max(xs)

# ------------------------------------------------------------------ paredes: contornos planos
for pc in pieces:
    segs = pc["segs"]
    def zb(seg, P):   # nunca por debajo del plano inferior del piso, ni en la cara interior ni en la exterior
        p = panels[seg["j"]]
        return max(P.z - T / abs(p["t"].y), floor_bottom_at(seg, v2(P) + seg["n"] * T)) - M_BAJO
    bot = [Vector((0.0, zb(segs[0], segs[0]["C0"])))]
    for i in range(len(segs) - 1):
        bot.append(Vector((segs[i]["S"] + segs[i]["flat"], (max if M_BAJO <= 0 else min)(zb(segs[i], segs[i]["C1"]), zb(segs[i + 1], segs[i + 1]["C0"])))))
    bot.append(Vector((pc["S"], zb(segs[-1], segs[-1]["C1"]))))
    def z_at(s_):
        for a, b in zip(bot[:-1], bot[1:]):
            if a.x - 1e-9 <= s_ <= b.x + 1e-9: return a.y + (b.y - a.y) * (s_ - a.x) / max(b.x - a.x, 1e-12)
        return bot[-1].y
    pc["muescas"] = []
    iv = sorted([seg["S"] + seg["a0"] + na, seg["S"] + seg["a0"] + nb, obn] for seg in segs for na, nb, obn in seg["notch"])
    merged = []
    for a_, b_, o_ in iv:
        if merged and a_ <= merged[-1][1] + 8.0: merged[-1][1] = max(merged[-1][1], b_)   # sin dedos de pared angostos
        else: merged.append([a_, b_, o_])
    for sa, sb, obn in merged:
        if M_BAJO > 0:
            za, zb2 = z_at(sa), z_at(sb)
            bot = ([q for q in bot if q.x <= sa + 1e-9] + [Vector((sa, za)), Vector((sa, za + M_BAJO))]
                   + [Vector((q.x, q.y + M_BAJO)) for q in bot if sa + 1e-9 < q.x < sb - 1e-9]
                   + [Vector((sb, zb2 + M_BAJO)), Vector((sb, zb2))] + [q for q in bot if q.x >= sb - 1e-9])
            pc["muescas"].append([round(sa, 2), round(sb, 2), obn])
            for sl in pc["slots"]:
                if min(q.x for q in sl) < sb and max(q.x for q in sl) > sa: rep["avisos"].append(f"{pc['name']}: ranura dentro de una muesca")
    for m in sorted(pc.get("muescas_pest", []), key=lambda m: m["J"].x):
        J, f2, hw, top = m["J"], m["f"], m["hw"], m["top"]; pp = Vector((-f2.y, f2.x))
        def side(sg):   # baja por el costado de la muesca hasta cortar el borde inferior de la pared
            lo, hi = -30.0, top
            for _ in range(60):
                mid = (lo + hi) / 2; P = J + f2 * (sg * hw) + pp * mid
                if P.y - z_at(P.x) > 0: hi = mid
                else: lo = mid
            return J + f2 * (sg * hw) + pp * hi
        A, D = side(-1), side(1); B, C = J - f2 * hw + pp * top, J + f2 * hw + pp * top
        x0, x1 = min(A.x, B.x), max(C.x, D.x)
        bot = [q for q in bot if q.x < x0 - 1e-6] + [A, B, C, D] + [q for q in bot if q.x > x1 + 1e-6]
    pc["outline"] = ccw([Vector((0.0, ZTOP)), Vector((pc["S"], ZTOP))] + list(reversed(bot)))
    if pc.get("muescas_pest"): pc["outline"] = dogbone(pc["outline"], hole=False, min_turn=45.0)
    pc["bend_s"] = [segs[i]["S"] + segs[i]["flat"] for i in range(len(segs) - 1)]
    pc["zmin"] = min(p.y for p in bot)

# ------------------------------------------------------------------ DXF + SVG
LAYERS = [("CORTE_EXTERIOR", 7), ("CORTE_INTERIOR", 1), ("RANURA_V", 5), ("TEXTO_NO_CORTAR", 3)]
def dxf(path, polys, lines_, texts):
    o = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
         "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(LAYERS))]
    for nm, col in LAYERS: o += ["0", "LAYER", "2", nm, "70", "0", "62", str(col), "6", "CONTINUOUS"]
    o += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    f = lambda v: "%.4f" % v
    for lay, pts in polys:
        o += ["0", "POLYLINE", "8", lay, "66", "1", "70", "1", "10", "0", "20", "0", "30", "0"]
        for p in pts: o += ["0", "VERTEX", "8", lay, "10", f(p.x), "20", f(p.y), "30", "0"]
        o += ["0", "SEQEND", "8", lay]
    for lay, a, b in lines_:
        o += ["0", "LINE", "8", lay, "10", f(a.x), "20", f(a.y), "30", "0", "11", f(b.x), "21", f(b.y), "31", "0"]
    for lay, p, h, txt in texts:
        o += ["0", "TEXT", "8", lay, "10", f(p.x), "20", f(p.y), "30", "0", "40", f(h), "1", txt]
    o += ["0", "ENDSEC", "0", "EOF"]
    with open(path, "w", newline="\r\n") as fh: fh.write("\n".join(o) + "\n")

drawings = {}
# piso: (x, u) ya es la vista desde abajo (cara B, la ranurada); se lleva al origen
xs = [p.x for p in floor_poly]; us = [p.y for p in floor_poly]
ox, oy = -min(xs), -min(us)
sh = lambda p: Vector((p.x + ox, p.y + oy))
fl_lines = []; fl_txt = []
for fd in folds:
    xa, xb = x_range_at_u(floor_poly, fd["u"])
    fl_lines.append(("RANURA_V", sh(Vector((xa, fd["u"]))), sh(Vector((xb, fd["u"])))))
    fl_txt.append(("TEXTO_NO_CORTAR", sh(Vector((xb + 4, fd["u"] - 1.2))), 3.0,
                   "PLIEGUE %.1f deg %s" % (fd["ang"], "(V CIERRA)" if fd["tipo"] == "normal" else "(INVERTIDO: V ABRE)")))
fl_txt += [("TEXTO_NO_CORTAR", sh(Vector((min(xs), max(us) + 8))), 4.0, "PISO BANDEJA CENTRAL - ACM 5 mm - x1"),
           ("TEXTO_NO_CORTAR", sh(Vector((min(xs), max(us) + 16))), 3.0, "CARA ARRIBA EN CNC: B (inferior). Ranuras V por esta cara. Cara A = donde ruedan los huevos"),
           ("TEXTO_NO_CORTAR", sh(Vector((min(xs), max(us) + 24))), 3.0, "Ranura V: dejar %.1f mm de material en el fondo" % RESTO)]
ref = [("TEXTO_NO_CORTAR", sh(Vector((min(xs), min(us) - 10))), sh(Vector((min(xs) + 100, min(us) - 10))))]
drawings["Piso"] = dict(polys=[("CORTE_EXTERIOR", [sh(p) for p in floor_poly])] + [("CORTE_INTERIOR", [sh(p) for p in h]) for h in FLOOR_HOLES],
                       lines=fl_lines + ref, texts=fl_txt + [
    ("TEXTO_NO_CORTAR", sh(Vector((min(xs), min(us) - 21))), 3.0, "Agujeros D4.1 = remaches ciegos de aluminio D4 cabeza redonda (colocar desde la cara A)"),
    ("TEXTO_NO_CORTAR", sh(Vector((min(xs), min(us) - 15))), 3.0, "Referencia 100 mm")])

for pc in pieces:
    def tr(p, pc=pc):
        s = pc["S"] - p.x if pc["mirror"] else p.x
        return Vector((s, p.y - pc["zmin"]))
    polys = ([("CORTE_EXTERIOR", [tr(p) for p in pc["outline"]])] + [("CORTE_INTERIOR", [tr(p) for p in sl]) for sl in pc["slots"]]
             + [("CORTE_INTERIOR", [tr(p) for p in h]) for h in pc["holes"]])
    ln = []; tx = []
    for k, sb in enumerate(pc["bend_s"]):
        a = tr(Vector((sb, ZTOP))); zb_ = min(p.y for p in pc["outline"] if abs(p.x - sb) < 1e-4)
        b = tr(Vector((sb, zb_)))
        ln.append(("RANURA_V", b, a))
        cn = pc["corners"][k]
        tx.append(("TEXTO_NO_CORTAR", a + Vector((1.0, 2.0)), 2.5, "%.1f" % cn["ang"]))
    lado = "A (interior)" if pc["cara"] == "A" else "B (exterior)"
    tx += [("TEXTO_NO_CORTAR", Vector((0, ZTOP - pc["zmin"] + 12)), 4.0, "PARED %s - ACM 5 mm - x1" % pc["name"].upper()),
           ("TEXTO_NO_CORTAR", Vector((0, ZTOP - pc["zmin"] + 6)), 3.0, "CARA ARRIBA EN CNC: %s. Ranuras V por esta cara; pliegues cierran la V" % lado)]
    drawings[pc["name"]] = dict(polys=polys, lines=ln, texts=tx)

for nm, dr in drawings.items():
    dxf(os.path.join(OUT, f"BandejaCentral_ACM5_{nm}.dxf"), dr["polys"], dr["lines"], dr["texts"])

# SVG: todas las piezas, apiladas
COL = {"CORTE_EXTERIOR": "#111", "CORTE_INTERIOR": "#d22", "RANURA_V": "#1565c0", "TEXTO_NO_CORTAR": "#2e7d32"}
svg = []; yoff = 0.0; Wmax = 0.0
for nm in ["Piso", "Pared_U", "Embudo_Izq", "Embudo_Der"]:
    dr = drawings[nm]
    pts = [p for _, ps in dr["polys"] for p in ps]
    x0, x1 = min(p.x for p in pts), max(p.x for p in pts); y0, y1 = min(p.y for p in pts), max(p.y for p in pts)
    ytxt = max([y1] + [p.y for _, p, _, _ in dr["texts"]]) + 6
    H = ytxt - min(y0, min([p.y for _, a, b in dr["lines"] for p in (a, b)] + [y0])) + 10
    base = yoff + ytxt
    Y = lambda y: base - y
    for lay, ps in dr["polys"]:
        svg.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="0.4"/>' % (
            " ".join("%.2f,%.2f" % (p.x + 10, Y(p.y)) for p in ps), "#e9eef3" if lay == "CORTE_EXTERIOR" else "#fff", COL[lay]))
    for lay, a, b in dr["lines"]:
        svg.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.5" stroke-dasharray="%s"/>' % (
            a.x + 10, Y(a.y), b.x + 10, Y(b.y), COL[lay], "3,2" if lay == "RANURA_V" else "none"))
    for lay, p, h, t_ in dr["texts"]:
        svg.append('<text x="%.2f" y="%.2f" font-size="%.1f" font-family="sans-serif" fill="%s">%s</text>' % (p.x + 10, Y(p.y), h, COL[lay], t_))
    yoff += H + 12; Wmax = max(Wmax, x1 + 20, 300)
with open(os.path.join(OUT, "BandejaCentral_ACM5_vista_previa.svg"), "w", encoding="utf-8") as fh:
    fh.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f" width="%.0fmm" height="%.0fmm"><rect width="100%%" height="100%%" fill="#fff"/>%s</svg>'
             % (Wmax, yoff, Wmax, yoff, "".join(svg)))

# ------------------------------------------------------------------ solidos 3D
def clip_strip(poly, lo, hi, axis):
    def clip(P, keep):
        out = []
        for i in range(len(P)):
            a, b = P[i - 1], P[i]; ka, kb = keep(a), keep(b)
            if kb:
                if not ka: out.append(inter(a, b))
                out.append(b)
            elif ka: out.append(inter(a, b))
        return out
    for lim, sgn in ((lo, 1), (hi, -1)):
        keep = lambda p, lim=lim, sgn=sgn: sgn * (p[axis] - lim) >= -1e-9
        def inter(a, b, lim=lim):
            t = (lim - a[axis]) / (b[axis] - a[axis]); return a + (b - a) * t
        poly = clip(poly, keep)
        if not poly: return []
    return poly
def dedup(lp):
    out = []
    for p in lp:
        if not out or (p - out[-1]).length > 1e-5: out.append(p)
    while len(out) > 1 and (out[0] - out[-1]).length <= 1e-5: out.pop()
    return out
def slab(bm, outer, holes, to3d, off):
    loops = [dedup(lp) for lp in [outer] + holes]
    flat = [p for lp in loops for p in lp]
    tris = tessellate_polygon([[Vector((p.x, p.y, 0)) for p in lp] for lp in loops])
    vi = [bm.verts.new(to3d(p)) for p in flat]; vo = [bm.verts.new(to3d(p) + off) for p in flat]
    for a, b, c in tris:
        for vv, rev in ((vi, False), (vo, True)):
            try: bm.faces.new((vv[a], vv[c], vv[b]) if rev else (vv[a], vv[b], vv[c]))
            except ValueError: pass
    k = 0
    for lp in loops:
        n = len(lp)
        for i in range(n):
            a, b = k + i, k + (i + 1) % n
            try: bm.faces.new((vi[a], vi[b], vo[b], vo[a]))
            except ValueError: pass
        k += n

coll = bpy.data.collections.get("Alucobond_BandejaCentral")
if not coll:
    coll = bpy.data.collections.new("Alucobond_BandejaCentral"); bpy.context.scene.collection.children.link(coll)
for ob in list(coll.objects): bpy.data.objects.remove(ob, do_unlink=True)
mat = bpy.data.materials.get("Alucobond_Gris") or bpy.data.materials.new("Alucobond_Gris")
mat.diffuse_color = (0.78, 0.80, 0.82, 1.0)
def make_obj(name, bm):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.scale(bm, vec=(0.001, 0.001, 0.001), verts=bm.verts)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); me.materials.append(mat); return ob

objs = {}
bm = bmesh.new()
for j, p in enumerate(panels):
    part = clip_strip(list(floor_poly), p["U0"], p["U0"] + p["L"], 1)
    hs = [h for h in FLOOR_HOLES if p["U0"] < sum(q.y for q in h) / len(h) < p["U0"] + p["L"]]
    if len(part) >= 3: slab(bm, part, hs, lambda q, j=j: floor3d(q.x, q.y, j), -p["n"] * T)
objs["Piso"] = make_obj("ACM_BandejaCentral_Piso", bm)
for pc in pieces:
    bm = bmesh.new()
    for s in pc["segs"]:
        lo, hi = s["S"], s["S"] + s["flat"]
        part = clip_strip(list(pc["outline"]), lo, hi, 0)
        holes = [sl for sl in pc["slots"] + pc["holes"] if lo < sum(q.x for q in sl) / len(sl) < hi]
        def to3d(q, s=s):
            P = v2(s["C0"]) + s["d"] * (q.x - s["S"] - s["a0"]); return Vector((P.x, P.y, q.y))
        if len(part) >= 3: slab(bm, part, holes, to3d, Vector((s["n"].x, s["n"].y, 0)) * T)
    objs[pc["name"]] = make_obj("ACM_BandejaCentral_" + pc["name"], bm)

def box(bm, o, A, B, C):
    P = [o + A * i + B * j + C * k for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    vs = [bm.verts.new(p) for p in P]
    for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([vs[i] for i in q])
bm = bmesh.new(); g = 0.2
for c in CLIPS:
    e3, u3, nf, nw, wdn, Jbo = c["e3"], c["u3"], c["nf"], c["nw"], c["wdn"], c["Jbo"]
    o = Jbo - e3 * (W_TAB / 2) + u3 * (CLIP_T + 0.1) - nf * 0.1
    box(bm, o, e3 * W_TAB, -u3 * CLIP_H, -nf * CLIP_T)                             # ala bajo el piso (y la pared)
    o2 = Jbo - e3 * (W_TAB / 2) + nw * 0.1 - wdn * 0.1
    box(bm, o2, e3 * W_TAB, -wdn * (CLIP_V - CLIP_T - 0.2), nw * CLIP_T)           # ala por fuera de la pared
mat_h = bpy.data.materials.get("Aluminio_Escuadras") or bpy.data.materials.new("Aluminio_Escuadras")
mat_h.diffuse_color = (0.55, 0.58, 0.62, 1.0)
_obh = make_obj("ACM_BandejaCentral_Escuadras", bm); _obh.data.materials[0] = mat_h
objs["Escuadras"] = _obh

from collections import Counter
angs = Counter(round(c["ang"]) for c in CLIPS)
with open(os.path.join(OUT, "BandejaCentral_ACM5_herrajes.txt"), "w", encoding="utf-8") as fh:
    W = fh.write
    W("BANDEJA CENTRAL - ALUCOBOND 5 mm - HERRAJES Y ARMADO\n\n")
    W(f"Remaches ciegos de aluminio D4 mm, cabeza redonda, largo 4x10 (agarre 6-8 mm): {2 * len(CLIPS)} (+10% de repuesto)\n")
    W("Agujeros D4.1 mm: ya vienen cortados por la CNC en el piso y en las paredes.\n\n")
    W(f"Escuadras de aluminio de 2 mm: {len(CLIPS)} piezas, {W_TAB:.0f} mm de ancho, ala bajo el piso de {CLIP_H:.0f} mm\n")
    W(f"  (desde la cara exterior de la pared) y ala exterior de {CLIP_V:.0f} mm (desde la cara inferior del piso).\n")
    W("  Van POR FUERA: abrazan la arista inferior-exterior de la union piso/pared. La pared termina al ras de la\n")
    W("  cara inferior del piso; lo unico que queda bajo el piso son los 2 mm del ala de la escuadra.\n")
    W("  Angulo interior de cada escuadra (cara inferior del piso / cara exterior de la pared):\n")
    for a, n in sorted(angs.items()): W(f"    {a} grados: {n} piezas\n")
    W(f"  Las de 90 grados: angulo extruido 20x20x2 (o {CLIP_H:.0f}x{CLIP_V:.0f}x2) cortado a {W_TAB:.0f} mm. Las demas: platina doblada al angulo.\n")
    W("  Agujero de la escuadra: taladrarlo a traves del agujero del panel ya armado (coincide exacto).\n\n")
    W("Detalle por escuadra (pieza, posicion s en el desarrollo sin espejar, angulo):\n")
    for c in CLIPS: W(f"  {c['pieza']:<11} s={c['s']:7.1f} mm  {c['ang']:5.1f} grados\n")
    W("\nRemaches del piso: se colocan desde arriba (cara de los huevos). La cabeza queda a 8 mm de la pared,\n")
    W("  zona que un huevo apoyado en la pared no alcanza.\n")
    W(f"Remaches de la pared: se colocan desde adentro (cabeza redonda por dentro), {RIV_PARED:.0f} mm sobre el piso;\n")
    W("  la cabeza queda en el rincon piso/pared, donde un huevo apoyado no llega.\n")
    W("Pestanas: entran en muescas abiertas en el borde inferior de la pared; la escuadra cierra la muesca por abajo.\n")
    W("Juntas pared U - embudo (esquinas de 144 grados): sellador/adhesivo; cada pared queda remachada al piso.\n")
    W("\nOrden de armado: 1) plegar el piso (adhesivo en las ranuras); 2) montar las paredes con las pestanas en\n")
    W("  sus muescas, plegando la pared U alrededor del piso; 3) sellador en las juntas U-embudo;\n")
    W("  4) presentar las escuadras por fuera, taladrar a traves de los agujeros y remachar.\n")

# ------------------------------------------------------------------ revision
dg = bpy.context.evaluated_depsgraph_get()
def bvh(o):
    oe = o.evaluated_get(dg); me = oe.to_mesh(); b = bmesh.new(); b.from_mesh(me); oe.to_mesh_clear()
    b.transform(o.matrix_world); t = BVHTree.FromBMesh(b); b.free(); return t
def closed(o):
    b = bmesh.new(); b.from_mesh(o.data); n = sum(1 for e in b.edges if not e.is_manifold); b.free(); return n
T_ = {k: bvh(o) for k, o in objs.items()}
rep["piso_vs_paredes"] = {k: len(T_["Piso"].overlap(T_[k])) for k in objs if k != "Piso"}
rep["paredes_entre_si"] = {f"{a}-{b}": len(T_[a].overlap(T_[b])) for a in objs for b in objs if a < b and "Piso" not in (a, b)}
rep["bordes_abiertos"] = {k: closed(o) for k, o in objs.items()}
others = [o for o in bpy.context.view_layer.objects if o.type == 'MESH' and o.visible_get() and o.name != src.name
          and o.name not in [x.name for x in objs.values()] and not o.name.startswith("Huevo")]
tsrc = bvh(src)
rep["choques_original"] = sorted({o.name for o in others if tsrc.overlap(bvh(o))})
rep["choques_nuevos"] = {k: sorted({o.name for o in others if T_[k].overlap(bvh(o))}) for k in objs}
rep["pliegues_piso"] = [dict(y=round(f["y"], 2), ang=round(f["ang"], 2), tipo=f["tipo"]) for f in folds]
rep["paredes"] = {pc["name"]: dict(largo_desarrollo=round(pc["S"], 2), alto=round(ZTOP - pc["zmin"], 2),
                                   esquinas=[round(c["ang"], 1) for c in pc["corners"]], ranuras=len(pc["slots"]),
                                   tramos=[round(s["flat"], 2) for s in pc["segs"]]) for pc in pieces}
rep["piso_desarrollo"] = [round(max(xs) - min(xs), 2), round(max(us) - min(us), 2)]
rep["pestanas"] = len(tabs_all)
rep["escuadras"] = {"n": len(CLIPS), "angulos": sorted({round(c["ang"], 1) for c in CLIPS})}
rep["travesano"] = [round(v, 2) for v in TRAV] if TRAV else None
rep["muescas"] = {pc["name"]: pc["muescas"] for pc in pieces if pc["muescas"]}
rep["pestanas_U"] = [t for t in tabs_all if t["pieza"] == "Pared_U"]
rep["salida"] = OUT
if "save" in argv:
    src.hide_set(True)
    bpy.ops.wm.save_mainfile(); rep["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(rep))
