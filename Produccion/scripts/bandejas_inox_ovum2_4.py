"""
Ovum2_4: bandejas SIMPLIFICADAS en chapa de acero inoxidable de 0.6 mm (corte a mano + plegado), con piezas PETG.

Idea
- Cada bandeja es UNA sola chapa: piso de 1 a 3 planos (pliegues suaves) + paredes rectas que se doblan hacia arriba
  desde el borde del piso. Las esquinas quedan abiertas (muesca en V) y se cierran con esquineros PETG remachados.
- Los embudos pequenos junto al girador (muchas caras chicas) pasan a "bocas" de PETG impresas (la cara de los huevos
  es la del modelo original). La chapa empieza en la "linea de boca" y se apoya sobre una ceja de la boca (remaches).
- Paredes simplificadas: se quitan vertices casi alineados y esquinas convexas pequenas (la bandeja nunca crece
  hacia la vecina, salvo el embudo de la central, que pasa a ser recto).
- Paredes compartidas: la central es duena de las paredes con LTop/RTop y LDown es duena de la pared del centro con
  RDown. La otra bandeja no tiene pared alli: solo una PESTANA de 10 mm (sobre el piso vecino) remachada a esa pared.
- Zocalos PETG (L bajo el piso + por fuera de la pared) en las paredes largas, solo donde caben (choques y espacio
  de los huevos de las bandejas de abajo). Esquineros PETG en cada esquina entre dos paredes propias.
- La superficie de los huevos queda donde estaba (salvo los pisos que se aplanan); la chapa crece hacia afuera.

Salidas
- Produccion/cnc/inox/<Bandeja>_INOX06_desarrollo.dxf  (desarrollo plano, cotas a la cara de los huevos)
- Produccion/stl/bandejas_inox/*.stl + Bandejas_inox_lista.txt
- Ovum2_4_inox.blend (copia; no toca Ovum2_4.blend) con colecciones INOX_Bandejas y PETG_Inox_*
Uso:  blender -b Ovum2_4.blend --python Produccion/scripts/bandejas_inox_ovum2_4.py -- [nosave]
Despues:  python Produccion/scripts/plantillas_pvc.py Produccion/cnc/inox *_INOX06_*.dxf carta
"""
import bpy, bmesh, sys, os, math, json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAVE = "nosave" not in argv
ROOT = os.path.dirname(bpy.data.filepath)
PROD = os.path.join(ROOT, "Produccion")
OUT_CNC = os.path.join(PROD, "cnc", "inox")
OUT_STL = os.path.join(PROD, "stl", "bandejas_inox")
for _d in (OUT_CNC, OUT_STL): os.makedirs(_d, exist_ok=True)
for _f in os.listdir(OUT_STL):        # sin restos de corridas anteriores
    if _f.lower().endswith(".stl"): os.remove(os.path.join(OUT_STL, _f))
BLEND_OUT = os.path.join(ROOT, "Ovum2_4_inox.blend")

# ------------------------------------------------------------------ parametros (mm)
T = 0.6          # chapa inox
CL = 0.1         # holgura PETG/chapa y chapa/chapa
DZ = -44.53      # las bandejas PVC de Ovum2_4 estan 44.53 mm mas abajo que las mallas Bandeja* originales
EGG_H = 42.5     # alto del huevo acostado (espacio reservado sobre los pisos de abajo)
PEST_H = 10.0    # pestana de union a la pared vecina (sobre el piso mas alto de los dos)
POST_W, POST_T, POST_S = 16.0, 2.5, 9.0     # esquinero: ala, espesor, remache a 9 mm de la esquina
ZOC_V, ZOC_H, ZOC_T = 15.0, 15.0, 2.5       # zocalo L: ala por fuera de la pared, ala bajo el piso, espesor
ZOC_MIN, ZOC_MAX, ZOC_END, ZOC_PASO = 60.0, 180.0, 22.0, 55.0
BOCA_T, LIP, LIP_T = 2.0, 14.0, 2.5         # boca PETG: espesor, ceja bajo la chapa, espesor de la ceja
R_INOX, R_PETG = 1.6, 2.2                   # remache 3 mm: D3.2 en inox, D4.4 impreso en PETG
TAG = "INOX06"
SAMPLES = 9

rep = {"avisos": [], "bandejas": {}, "petg": {}, "choques": []}
def aviso(s): rep["avisos"].append(s); print("AVISO:", s)

# ------------------------------------------------------------------ utilidades 2D / planos
def V2(p): return Vector((p.x, p.y))
def perp(v): return Vector((-v.y, v.x))
def cross2(a, b): return a.x * b.y - a.y * b.x
def area2(P): return 0.5 * sum(P[i].x * P[(i + 1) % len(P)].y - P[(i + 1) % len(P)].x * P[i].y for i in range(len(P)))
def inside2(pt, P):
    c = False; n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        if (a.y > pt.y) != (b.y > pt.y) and pt.x < (b.x - a.x) * (pt.y - a.y) / (b.y - a.y) + a.x: c = not c
    return c
def line_x(p1, d1, p2, d2):
    den = cross2(d1, d2)
    return None if abs(den) < 1e-9 else p1 + d1 * (cross2(p2 - p1, d2) / den)
def seg_x(a, b, c, d):
    """interseccion propia de segmentos 2D"""
    r, s = b - a, d - c; den = cross2(r, s)
    if abs(den) < 1e-9: return False
    t = cross2(c - a, s) / den; u = cross2(c - a, r) / den
    return 1e-4 < t < 1 - 1e-4 and 1e-4 < u < 1 - 1e-4
def pz(pl, p): return pl[0] * p.x + pl[1] * p.y + pl[2]
def pnorm(pl): return Vector((-pl[0], -pl[1], 1.0)).normalized()
def solve3(M, v):
    """sistema 3x3 en doble precision (mathutils es float32)"""
    def det(m): return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    D = det(M); out = []
    for c in range(3):
        Mc = [[v[r] if k == c else M[r][k] for k in range(3)] for r in range(3)]
        out.append(det(Mc) / D)
    return tuple(out)
def pl3(p, q, r):
    return solve3([[float(p.x), float(p.y), 1.0], [float(q.x), float(q.y), 1.0], [float(r.x), float(r.y), 1.0]], [float(p.z), float(q.z), float(r.z)])
def plfit(P):
    A = [[0.0] * 3 for _ in range(3)]; b = [0.0] * 3
    for p in P:
        rr = (float(p.x), float(p.y), 1.0)
        for i in range(3):
            b[i] += rr[i] * float(p.z)
            for j in range(3): A[i][j] += rr[i] * rr[j]
    return solve3(A, b)
def pl_line_fit(a, b, others):
    """plano que contiene exactamente la recta a-b (linea de boca) y ajusta los demas puntos"""
    d = V2(b - a); g0 = d * ((b.z - a.z) / d.length_squared); m = perp(d).normalized()
    num = sum((p.z - a.z - g0.dot(V2(p - a))) * m.dot(V2(p - a)) for p in others)
    den = sum(m.dot(V2(p - a)) ** 2 for p in others)
    g = g0 + m * (num / den)
    return (g.x, g.y, a.z - g.x * a.x - g.y * a.y)
def clip(P, f):
    out = []; n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]; fa, fb = f(a), f(b)
        if fa >= 0: out.append(a)
        if (fa >= 0) != (fb >= 0): out.append(a + (b - a) * (fa / (fa - fb)))
    return out

# ------------------------------------------------------------------ mallas originales
def src(name):
    o = bpy.data.objects[name]; mw = o.matrix_world
    V = [(mw @ v.co) * 1000.0 + Vector((0, 0, DZ)) for v in o.data.vertices]
    F = [list(p.vertices) for p in o.data.polygons]
    N = [(mw.to_3x3() @ p.normal).normalized() for p in o.data.polygons]
    return V, F, N
SRC = {n: src(n) for n in ["BandejaCentral", "BandejaLTop", "BandejaRTop", "BandejaLDown", "BandejaRDown"]}

def src_tops(name):
    """aristas superiores de las paredes originales (para la altura de las paredes nuevas)"""
    V, F, N = SRC[name]; segs = []
    for f, n in zip(F, N):
        if abs(n.z) > 0.3: continue
        P = sorted((V[i] for i in f), key=lambda p: -p.z)[:2]
        segs.append((P[0], P[1]))
    return segs
def top_src(name, p):
    best = None
    for a, b in src_tops(name):
        d = V2(b - a); L2 = d.length_squared
        t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, (V2(p) - V2(a)).dot(d) / L2))
        q = V2(a) + d * t; dist = (q - V2(p)).length
        if best is None or dist < best[0]: best = (dist, a.z + (b.z - a.z) * t)
    return best[1]

def bvh_of(bm):
    b = bm.copy(); bmesh.ops.triangulate(b, faces=b.faces); t = BVHTree.FromBMesh(b); b.free(); return t

# obstaculos de la escena
IGN = ("PVC_", "PETG_Zocalo", "PETG_Cuna", "PETG_Escuadras", "Bandeja", "Huevo", "INOX_", "PETG_Inox")
dg = bpy.context.evaluated_depsgraph_get()
OBST = []
for o in bpy.context.view_layer.objects:
    if o.type != "MESH" or o.hide_get() or o.name.startswith(IGN): continue
    bb = [o.matrix_world @ Vector(c) * 1000 for c in o.bound_box]
    if max(p.z for p in bb) < -10 or min(p.z for p in bb) > 200 or max(p.y for p in bb) < -60 or min(p.y for p in bb) > 620: continue
    ev = o.evaluated_get(dg); me = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); bm.transform(Matrix.Scale(1000, 4) @ o.matrix_world); ev.to_mesh_clear()
    OBST.append((o.name, bvh_of(bm))); bm.free()
print("obstaculos:", len(OBST))


# ------------------------------------------------------------------ definicion de las bandejas simplificadas
TR = {}
OFF = T + CL + T     # cara de huevos de una pestana respecto de la cara de huevos de la pared vecina

def chain_k(pls, p):
    """planos en cadena (boca -> fondo): se parte del plano del fondo y se avanza hacia la boca mientras el plano
    anterior este mas alto (pliegues en valle). Asi una rampa inclinada de costado no invade el fondo."""
    k = len(pls) - 1
    while k > 0 and pz(pls[k - 1], p) >= pz(pls[k], p): k -= 1
    return k
def xreg_k(tr, p):
    """regiones explicitas (pliegues entre vertices del contorno): la que contiene p, o la mas cercana"""
    best = None
    for k, (pl, P) in enumerate(tr["xregs"]):
        if inside2(p, P): return k
        d = min((p - (P[i] + (P[(i + 1) % len(P)] - P[i]) * max(0.0, min(1.0, (p - P[i]).dot(P[(i + 1) % len(P)] - P[i]) / max((P[(i + 1) % len(P)] - P[i]).length_squared, 1e-9))))).length for i in range(len(P)))
        if best is None or d < best[0]: best = (d, k)
    return best[1]
def plane_k(tr, p): return xreg_k(tr, p) if tr.get("xregs") else chain_k(tr["planes"], p)
def floor_z(tr, p): return pz(tr["planes"][plane_k(tr, p)], p)

def mk(name, planes, poly, kinds, neigh=None, xregs=None):
    poly = [V2(p) for p in poly]
    if area2(poly) < 0:
        n = len(poly); poly = poly[::-1]; kinds = [kinds[(n - 2 - j) % n] for j in range(n)]
    TR[name] = {"name": name, "planes": planes, "poly0": poly, "kinds0": kinds, "neigh": neigh,
                "xregs": [(pl, [V2(q) for q in P] if area2([V2(q) for q in P]) > 0 else [V2(q) for q in P][::-1]) for pl, P in xregs] if xregs else None}

def def_central():
    V = SRC["BandejaCentral"][0]
    A = pl3(V[12], V[13], V[4]); B = (0.0, 0.0, V[1].z)
    mk("BandejaCentral", [A, B], [V[12], V[13], V[4], V[28], V[22], V[1]],
       ["boca", "pared", "pared", "pared", "pared", "pared"])

def def_top(name, sx):
    V = SRC[name][0]; Vc = SRC["BandejaCentral"][0]
    f0, f1 = (Vc[12], Vc[1]) if sx < 0 else (Vc[13], Vc[4])
    d = V2(f1 - f0).normalized(); nrm = perp(d)
    if nrm.x * sx < 0: nrm = -nrm
    o0 = V2(f0) + nrm * OFF
    xs = f1.x + sx * OFF
    I = line_x(V2(V[13]), V2(V[3] - V[13]), o0, d)
    J = line_x(o0, d, Vector((xs, 0)), Vector((0, 1)))
    K = line_x(V2(V[1]), V2(V[4] - V[1]), Vector((xs, 0)), Vector((0, 1)))
    A = pl_line_fit(V[12], V[13], [V[20], V[0], V[3]]); B = (0.0, 0.0, V[1].z)
    mk(name, [A, B], [V[12], V[13], I, J, K, V[1], V[26], V[20]],
       ["boca", "pared", "pest", "pest", "pared", "pared", "pared", "pared"], neigh="BandejaCentral")

def def_down(name, sx):
    V = SRC[name][0]
    owner = sx < 0                          # LDown es duena de la pared del centro; RDown pone pestana
    xc = sx * 0.3 if owner else sx * (0.3 + CL + T)    # pared centrada en x=0 (cara de huevos LDown a -0.3)
    v8 = Vector((xc, V[8].y)); v4 = Vector((xc, V[4].y))
    # rampa original alabeada -> rampa de la boca (P1) + 2 triangulos (pliegues 26-29, 26-11, 12-11) + fondo (M)
    P1 = pl_line_fit(V[18], V[21], [V[26], V[29]])
    M = plfit([V[i] for i in (12, 11, 0, 8, 2, 6, 4)])
    def at(pl, p): return Vector((p.x, p.y, pz(pl, p)))
    Tb = pl3(at(P1, V[26]), at(P1, V[29]), at(M, V[11]))
    Ta = pl3(at(P1, V[26]), at(M, V[12]), at(M, V[11]))
    xr = [(P1, [V[18], V[26], V[29], V[21]]), (Tb, [V[26], V[11], V[29]]), (Ta, [V[26], V[12], V[11]]), (M, [V[12], V[2], v4, v8, V[11]])]
    mk(name, [P1, Tb, Ta, M], [V[18], V[26], V[12], V[2], v4, v8, V[11], V[29], V[21]],
       ["pared", "pared", "pared", "pared", "pared" if owner else "pest", "pared", "pared", "pared", "boca"],
       neigh=None if owner else "BandejaLDown", xregs=xr)

def_central(); def_top("BandejaLTop", -1); def_top("BandejaRTop", +1); def_down("BandejaLDown", -1); def_down("BandejaRDown", +1)
UPPER = ("BandejaCentral", "BandejaLTop", "BandejaRTop"); LOWER = ("BandejaLDown", "BandejaRDown")
MOUTH = {"BandejaCentral": (12, 13), "BandejaLTop": (12, 13), "BandejaRTop": (12, 13), "BandejaLDown": (18, 21), "BandejaRDown": (18, 21)}

# ------------------------------------------------------------------ geometria de cada bandeja
def build_outline(tr):
    P, K = tr["poly0"], tr["kinds0"]; pls = tr["planes"]; n = len(P)
    if tr.get("xregs"):
        tr["poly"], tr["kinds"], tr["crease"] = list(P), list(K), [False] * n
        tr["regs"] = [{"k": k, "pl": pl, "poly": Q} for k, (pl, Q) in enumerate(tr["xregs"])]
        tr["region_of"] = lambda p: xreg_k(tr, p)
        return
    pts, kinds, crease = [], [], []
    def amax(p): return chain_k(pls, p)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        pts.append(a); kinds.append(K[i]); crease.append(False)
        ts = []
        for k in range(len(pls) - 1):
            j = k + 1
            fa = pz(pls[k], a) - pz(pls[j], a); fb = pz(pls[k], b) - pz(pls[j], b)
            if fa * fb < 0: ts.append(fa / (fa - fb))
        for t in sorted(ts):
            q = a + (b - a) * t
            if amax(a + (b - a) * max(0, t - 1e-4)) != amax(a + (b - a) * min(1, t + 1e-4)) and (q - a).length > 0.5 and (q - b).length > 0.5:
                pts.append(q); kinds.append(K[i]); crease.append(True)
    tr["poly"], tr["kinds"], tr["crease"] = pts, kinds, crease
    regs = []
    for k, pl in enumerate(pls):
        R = list(pts)
        cuts = ([(pls[k], pls[k - 1], -1e-6)] if k > 0 else []) + [(pls[m], pls[m + 1], 1e-6) for m in range(k, len(pls) - 1)]
        for pa, pb, e in cuts:
            R = clip(R, lambda p, pa=pa, pb=pb, e=e: pz(pa, p) - pz(pb, p) + e)
            if len(R) < 3: break
        R = [p for i, p in enumerate(R) if (p - R[i - 1]).length > 1e-3] if len(R) >= 3 else []
        if len(R) >= 3 and abs(area2(R)) > 1.0: regs.append({"k": k, "pl": pl, "poly": R})
    tr["regs"] = regs
    def region_of(p):
        k = chain_k(pls, p)
        return next(i for i, r in enumerate(regs) if r["k"] == k)
    tr["region_of"] = region_of

def wall_tops(tr):
    """lista de paredes/pestanas: cara de huevos A,B (piso) y At,Bt (borde superior)"""
    n = len(tr["poly"]); segs = []
    for i in range(n):
        kind = tr["kinds"][i]
        if kind == "boca": segs.append(None); continue
        a, b = tr["poly"][i], tr["poly"][(i + 1) % n]
        za, zb = floor_z(tr, a), floor_z(tr, b)
        if kind == "pared":
            req = lambda p: top_src(tr["name"], p)
        else:
            nb = TR[tr["neigh"]]
            req = lambda p, nb=nb: max(floor_z(tr, p), floor_z(nb, p) - T) + PEST_H
        ta, tb = req(a), req(b)
        lift = max(0.0, max(req(a + (b - a) * (s / SAMPLES)) - (ta + (tb - ta) * s / SAMPLES) for s in range(SAMPLES + 1)))
        if kind == "pest": ta += lift; tb += lift
        # bajar el borde si algo de la maquina pasa por encima de la pared (p. ej. travesano del bastidor)
        d_ = (b - a).normalized(); n_ = Vector((d_.y, -d_.x)); drop = 0.0; L_ = (b - a).length
        for s_ in range(int(L_ / 3) + 1):
            q = a + (b - a) * (s_ * 3 / L_ if L_ > 0 else 0)
            zt = ta + (tb - ta) * (s_ * 3 / L_ if L_ > 0 else 0); zf = floor_z(tr, q)
            for off in (0.0, T * 0.5, T):
                o3 = Vector((q.x + n_.x * off, q.y + n_.y * off, zf + 2.0))
                for nm_, b_ in OBST:
                    hit = b_.ray_cast(o3, Vector((0, 0, 1)), zt - zf + 2.0)
                    if hit[0] is not None and hit[0].z < zt + 1.0: drop = max(drop, zt + 1.0 - hit[0].z)
        if drop > 0:
            ta -= drop; tb -= drop
            aviso(f"{tr['name']} pared {i}: borde bajado {drop:.1f} mm para librar la maquina")
        A = Vector((a.x, a.y, za)); B = Vector((b.x, b.y, zb))
        At = Vector((a.x, a.y, ta)); Bt = Vector((b.x, b.y, tb))
        d = (b - a).normalized(); nout = Vector((d.y, -d.x))
        hmin = min(ta - za, tb - zb)
        if hmin < 4: aviso(f"{tr['name']} pared {i}: altura minima {hmin:.1f} mm")
        segs.append({"i": i, "kind": kind, "A": A, "B": B, "At": At, "Bt": Bt, "a": a, "b": b, "n": nout,
                     "reg": tr["region_of"]((a + b) / 2 - nout * 0.5), "len": (b - a).length})
    tr["segs"] = segs

for nm in ["BandejaCentral", "BandejaLTop", "BandejaRTop", "BandejaLDown", "BandejaRDown"]:
    build_outline(TR[nm])
for nm in ["BandejaCentral", "BandejaLTop", "BandejaRTop", "BandejaLDown", "BandejaRDown"]:
    wall_tops(TR[nm])

# desviacion del piso nuevo respecto del original (fuera de la boca)
for nm, tr in TR.items():
    V, F, N = SRC[nm]; dev = []
    ia, ib = MOUTH[nm]; ma, mb = V2(V[ia]), V2(V[ib])
    inner = sum((V2(p) for p in tr["poly"]), Vector((0, 0))) / len(tr["poly"])
    sgn = 1 if cross2(mb - ma, inner - ma) > 0 else -1
    for f, n in zip(F, N):
        if abs(n.z) < 0.5: continue
        for i in f:
            p = V[i]
            if sgn * cross2(mb - ma, V2(p) - ma) < 0.5: continue
            c_ = sum(tr["poly"], Vector((0, 0))) / len(tr["poly"]); q_ = V2(p) + (c_ - V2(p)).normalized() * 0.5
            if inside2(q_, tr["poly"]): dev.append((round(floor_z(tr, V2(p)) - p.z, 1), i))
    tr["dev"] = (min(dev), max(dev)) if dev else (0, 0)
    tr["dev_all"] = sorted(set(dev))

if "geo" in argv:
    L_ = lambda v: [round(x, 2) for x in v]
    json.dump({nm: {"poly": [L_(p) for p in tr["poly"]], "kinds": tr["kinds"], "planes": tr["planes"],
                    "regs": [{"k": r["k"], "poly": [L_(p) for p in r["poly"]]} for r in tr["regs"]],
                    "segs": [None if not s_ else {k_: L_(s_[k_]) for k_ in ("A", "B", "At", "Bt")} for s_ in tr["segs"]]}
               for nm, tr in TR.items()}, open(os.path.join(OUT_STL, "debug_geo.json"), "w"))
    raise SystemExit

# ------------------------------------------------------------------ mallas (en mm) y objetos
def bm_box(bm, P8):
    """hexaedro: P8 = 4 de abajo (en orden) + 4 de arriba"""
    vs = [bm.verts.new(p) for p in P8]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([vs[i] for i in f])
def bm_prism(bm, poly2, zb, zt):
    """prisma vertical; zb/zt pueden ser funciones del punto"""
    n = len(poly2)
    if area2(poly2) < 0: poly2 = poly2[::-1]
    fb = zb if callable(zb) else (lambda p: zb); ft = zt if callable(zt) else (lambda p: zt)
    lo = [bm.verts.new((p.x, p.y, fb(p))) for p in poly2]; hi = [bm.verts.new((p.x, p.y, ft(p))) for p in poly2]
    bm.faces.new(lo[::-1]); bm.faces.new(hi)
    for i in range(n):
        j = (i + 1) % n; bm.faces.new([lo[i], lo[j], hi[j], hi[i]])
def bm_slab(bm, poly3, nrm, t):
    """placa: poligono 3D plano (cara superior) y espesor t hacia -nrm"""
    if (poly3[1] - poly3[0]).cross(poly3[2] - poly3[1]).dot(nrm) < 0: poly3 = poly3[::-1]
    hi = [bm.verts.new(p) for p in poly3]; lo = [bm.verts.new(p - nrm * t) for p in poly3]
    bm.faces.new(hi); bm.faces.new(lo[::-1]); n = len(poly3)
    for i in range(n):
        j = (i + 1) % n; bm.faces.new([hi[j], hi[i], lo[i], lo[j]])

def sheet_bm(tr):
    bm = bmesh.new()
    for r in tr["regs"]:
        bm_slab(bm, [Vector((p.x, p.y, pz(r["pl"], p))) for p in r["poly"]], pnorm(r["pl"]), T)
    for s in tr["segs"]:
        if not s: continue
        n3 = Vector((s["n"].x, s["n"].y, 0)); dz = Vector((0, 0, T))
        P = [s["A"] - dz, s["B"] - dz, s["B"] - dz + n3 * T, s["A"] - dz + n3 * T,
             s["At"], s["Bt"], s["Bt"] + n3 * T, s["At"] + n3 * T]
        bm_box(bm, P)
    return bm

SHEET_BM = {nm: sheet_bm(tr) for nm, tr in TR.items()}
SHEET_BVH = {nm: bvh_of(bm) for nm, bm in SHEET_BM.items()}

# espacio de los huevos de las bandejas de abajo
EGG_BM = bmesh.new()
for nm in LOWER:
    for r in TR[nm]["regs"]:
        P = r["poly"]; c = sum(P, Vector((0, 0))) / len(P)
        Pin = [c + (p - c) * 0.985 for p in P]
        bm_prism(EGG_BM, Pin, lambda p, pl=r["pl"]: pz(pl, p) + 0.5, lambda p, pl=r["pl"]: pz(pl, p) + EGG_H)
EGG_BVH = bvh_of(EGG_BM)

def where(bvh, other):
    """caja aproximada (mm) de los triangulos que se cruzan"""
    pr = bvh.overlap(other)
    if not pr: return None
    pts = []
    for i, _ in pr[:400]:
        loc = None
        pts.append(i)
    return len(pr)
def hits(bvh, skip_trays=(), egg=False, petg=(), loc=None):
    out = []
    def chk(nm, b):
        pr = bvh.overlap(b)
        if not pr: return
        if loc is not None:
            P = [loc[i] for i, _ in pr[:2000] if i in loc]
            if P:
                lo = [round(min(p[k] for p in P)) for k in range(3)]; hi = [round(max(p[k] for p in P)) for k in range(3)]
                out.append(f"{nm} {lo}..{hi}"); return
        out.append(nm)
    for nm, b in OBST: chk(nm, b)
    for nm, b in SHEET_BVH.items():
        if nm in skip_trays: continue
        chk("INOX_" + nm, b)
    if egg: chk("espacio huevos (abajo)", EGG_BVH)
    for nm, b in petg: chk(nm, b)
    return out
def tri_loc(bm):
    b = bm.copy(); bmesh.ops.triangulate(b, faces=b.faces); b.faces.ensure_lookup_table()
    d = {f.index: f.calc_center_median().copy() for f in b.faces}; b.free(); return d

# choques de las chapas
for nm in TR:
    h = hits(SHEET_BVH[nm], skip_trays=(nm,), egg=nm in UPPER, loc=tri_loc(SHEET_BM[nm]))
    if h: rep["choques"].append({"pieza": "INOX_" + nm, "con": h}); aviso(f"chapa {nm} toca: {h}")

def src_bvh(nm):
    V, F, N = SRC[nm]; return BVHTree.FromPolygons(V, F)
def gap_report(up, lo):
    """hueco vertical (mm) entre la cara inferior de la bandeja de arriba y el techo de un huevo sobre la de abajo"""
    Bu, Bl = src_bvh(up), src_bvh(lo); tu, tl = TR[up], TR[lo]
    res = {"nuevo": None, "original": None}
    xs = [p.x for p in tl["poly"]]; ys = [p.y for p in tl["poly"]]
    for x in range(int(min(xs)), int(max(xs)), 4):
        for y in range(int(min(ys)), int(max(ys)), 4):
            q = Vector((x, y))
            if not (inside2(q, tu["poly"]) and inside2(q, tl["poly"])): continue
            if min((q - p).length for p in tl["poly"]) < 15: continue
            g = floor_z(tu, q) - T / pnorm(tu["planes"][plane_k(tu, q)]).z - (floor_z(tl, q) + EGG_H)
            if res["nuevo"] is None or g < res["nuevo"][0]: res["nuevo"] = (round(g, 1), x, y)
            hu = Bu.ray_cast(Vector((x, y, 400)), Vector((0, 0, -1))); hl = Bl.ray_cast(Vector((x, y, 400)), Vector((0, 0, -1)))
            if hu[0] is not None and hl[0] is not None:
                hl2 = Bl.ray_cast(Vector((x, y, hu[0].z - 1.0)), Vector((0, 0, -1)))
                if hl2[0] is not None:
                    g0 = hu[0].z - 2.0 - (hl2[0].z + EGG_H)
                    if res["original"] is None or g0 < res["original"][0]: res["original"] = (round(g0, 1), x, y)
    return res
rep["hueco_huevos"] = {f"{u}/{l}": gap_report(u, l) for u, l in (("BandejaLTop", "BandejaLDown"), ("BandejaRTop", "BandejaRDown"),
                                                                  ("BandejaCentral", "BandejaLDown"), ("BandejaCentral", "BandejaRDown"))}
print("HUECO", rep["hueco_huevos"])

# ------------------------------------------------------------------ agujeros (remaches) registrados en 3D
HOLES = []      # (punto cara huevos, eje, origen)
def add_hole(p, axis, why): HOLES.append((p.copy(), axis.normalized(), why))

# ------------------------------------------------------------------ PETG
PETG = []       # dict(name, bm, holes:[(p,axis)], cat)
PETG_BVH = []
def try_petg(name, bm, holes, cat, tray, egg_check=True, force=False, quiet=False):
    b = bvh_of(bm)
    h = hits(b, egg=egg_check and tray not in LOWER, petg=PETG_BVH)
    if h and not force:
        if not quiet: rep["petg"].setdefault("descartadas", []).append({"pieza": name, "con": h})
        bm.free(); return False
    if h: rep["choques"].append({"pieza": name, "con": h}); aviso(f"{name} toca {h}")
    PETG.append({"name": name, "bm": bm, "holes": holes, "cat": cat, "tray": tray}); PETG_BVH.append((name, b))
    for p, ax in holes: add_hole(p, ax, name)
    return True

# --- bocas: el embudo original desde la corona hasta la linea de boca
def boca(nm):
    V, F, N = SRC[nm]; tr = TR[nm]; ia, ib = MOUTH[nm]
    ma, mb = V2(V[ia]), V2(V[ib]); inner = sum((V2(p) for p in tr["poly"]), Vector((0, 0))) / len(tr["poly"])
    sgn = 1 if cross2(mb - ma, inner - ma) > 0 else -1
    side = lambda p: sgn * cross2((mb - ma).normalized(), V2(p) - ma)
    bm = bmesh.new(); vmap = {}
    for f in F:
        if all(side(V[i]) <= 0.3 for i in f):
            vs = []
            for i in f:
                if i not in vmap: vmap[i] = bm.verts.new(V[i])
                vs.append(vmap[i])
            try: bm.faces.new(vs)
            except ValueError: pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.01)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # las normales deben apuntar hacia afuera (piso hacia abajo)
    fl = [f for f in bm.faces if abs(f.normal.z) > 0.5]
    if fl and sum(f.normal.z for f in fl) > 0: bmesh.ops.reverse_faces(bm, faces=bm.faces)
    me = bpy.data.meshes.new("tmp_boca"); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new("tmp_boca", me); bpy.context.scene.collection.objects.link(ob)
    md = ob.modifiers.new("s", "SOLIDIFY"); md.thickness = BOCA_T; md.offset = 1.0; md.use_even_offset = True; md.use_rim = True
    dg2 = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg2)
    bm2 = bmesh.new(); bm2.from_mesh(ev.to_mesh()); ev.to_mesh_clear()
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
    d = (mb - ma).normalized(); nin = perp(d) * sgn
    # cortar la boca a CL antes de la linea de boca (tope contra la chapa) y cerrar el corte
    n3 = Vector((nin.x, nin.y, 0.0)); c3 = Vector((ma.x, ma.y, 0.0)) - n3 * CL
    geo = bm2.verts[:] + bm2.edges[:] + bm2.faces[:]
    bmesh.ops.bisect_plane(bm2, geom=geo, plane_co=c3, plane_no=n3, clear_outer=True, dist=1e-4)
    bnd = [e for e in bm2.edges if e.is_boundary]
    if bnd: bmesh.ops.holes_fill(bm2, edges=bnd, sides=0)
    bmesh.ops.recalc_face_normals(bm2, faces=bm2.faces)
    # ceja bajo la chapa
    pl = tr["planes"][tr["region_of"](inner)] if False else None
    def under(p): return floor_z(tr, p) - T / pnorm(tr["planes"][plane_k(tr, p)]).z - CL
    L0, L1 = ma - d * 0.0 - nin * 3.0, mb + d * 0.0 - nin * 3.0
    Q = [L0, L1, L1 + nin * (LIP + 3.0), L0 + nin * (LIP + 3.0)]
    def ufix(p): return under(p if side(p) > 0.05 else p + nin * (0.06 - side(p)))
    lip = bmesh.new(); bm_prism(lip, Q, lambda p: ufix(p) - LIP_T, lambda p: ufix(p))
    holes = []
    for t in (0.25, 0.75):
        q = ma + (mb - ma) * t + nin * (LIP * 0.55)
        holes.append((Vector((q.x, q.y, floor_z(tr, q))), pnorm(tr["regs"][tr["region_of"](q)]["pl"])))
    return bm2, lip, holes

BOCA_PARTS = {}
for nm in TR:
    b, lip, holes = boca(nm)
    BOCA_PARTS[nm] = (b, lip, holes)

# --- esquineros (dentro de una bandeja o entre paredes de dos bandejas que se juntan)
def under_z(tr, p): return floor_z(tr, p) - T / pnorm(tr["planes"][plane_k(tr, p)]).z
def topw(s, p):
    t = (V2(p) - s["a"]).dot(s["b"] - s["a"]) / (s["b"] - s["a"]).length_squared
    return s["At"].z + (s["Bt"].z - s["At"].z) * t
def egg_ceiling(p):
    """techo del espacio de huevos de las bandejas de abajo en p (o -inf)"""
    z = -1e9
    for nm in LOWER:
        if inside2(p, TR[nm]["poly"]): z = max(z, floor_z(TR[nm], p) + EGG_H + 0.5)
    return z
def post(EA, sA, trA, EB, sB, trB, W=POST_W, lift_egg=False):
    gap = CL if trA is trB else CL + 0.25      # entre bandejas: mas holgura (los cantos de las dos chapas se cruzan)
    """esquinero: ala sobre la pared A (desde su extremo EA) y ala sobre la pared B (desde EB)"""
    uA = (sA["b"] - sA["a"]).normalized() * (1 if (EA - sA["a"]).length < 1e-3 else -1)
    uB = (sB["b"] - sB["a"]).normalized() * (1 if (EB - sB["a"]).length < 1e-3 else -1)
    WA, WB = min(W, sA["len"] * 0.45), min(W, sB["len"] * 0.45)
    nA, nB = sA["n"], sB["n"]
    def ring(dl):
        pA, pB = EA + nA * dl, EB + nB * dl
        c = line_x(pA, uA, pB, uB)
        if c is None or (c - (pA + pB) / 2).length > 6: c = (pA + pB) / 2
        return [pA + uA * WA, c, pB + uB * WB]
    a, b = ring(T + gap), ring(T + gap + POST_T)
    poly = a + b[::-1]
    for i in range(len(poly)):
        for k in range(i + 2, len(poly)):
            if (i, k) != (0, len(poly) - 1) and seg_x(poly[i], poly[(i + 1) % len(poly)], poly[k], poly[(k + 1) % len(poly)]): return None
    footA, footB = [EA, EA + uA * WA], [EB, EB + uB * WB]
    zb = max([under_z(trA, p) for p in footA] + [under_z(trB, p) for p in footB])
    if lift_egg: zb = max([zb] + [egg_ceiling(p) for p in poly])
    zt = min([topw(sA, p) for p in footA] + [topw(sB, p) for p in footB]) - 0.5
    if zt - zb < 12: return None
    bm = bmesh.new(); bm_prism(bm, poly, zb, zt)
    h = zt - zb; zs = [zb + h * 0.5] if h < 30 else [zb + h * 0.3, zb + h * 0.75]
    holes = []
    for E, u, w, nn in ((EA, uA, WA, nA), (EB, uB, WB, nB)):
        q = E + u * min(POST_S, w * 0.6)
        for z in zs: holes.append((Vector((q.x, q.y, z)), Vector((nn.x, nn.y, 0))))
    return bm, holes

# --- zocalos: L (ala bajo el piso + ala por fuera de la pared) o, si no cabe, solo una de las alas
ZOC_SEC = {"L": [(-ZOC_H, -CL), (-ZOC_H, -CL - ZOC_T), (T + CL + ZOC_T, -CL - ZOC_T), (T + CL + ZOC_T, ZOC_V), (T + CL, ZOC_V), (T + CL, -CL)],
           "piso": [(-ZOC_H, -CL), (-ZOC_H, -CL - ZOC_T), (-0.5, -CL - ZOC_T), (-0.5, -CL)],
           "pared": [(T + CL, -CL), (T + CL + ZOC_T, -CL), (T + CL + ZOC_T, ZOC_V), (T + CL, ZOC_V)]}
def zocalo(tr, s, s0, s1, mode="L"):
    a, b, nn = s["a"], s["b"], s["n"]; d = (b - a).normalized()
    reg = tr["regs"][s["reg"]]; pl = reg["pl"]
    def und(p): return pz(pl, p) - T / pnorm(pl).z
    sec = ZOC_SEC[mode]; m = len(sec)
    bm = bmesh.new(); rings = []
    for sp in (s0, s1):
        base = a + d * sp; ring = []
        for nv, dz in sec:
            p = base + nn * nv; zref = und(p) if nv < 0 else und(base)
            ring.append(bm.verts.new((p.x, p.y, zref + dz)))
        rings.append(ring)
    r0, r1 = rings
    bm.faces.new(r0[::-1]); bm.faces.new(r1)
    for i in range(m):
        j = (i + 1) % m; bm.faces.new([r0[i], r0[j], r1[j], r1[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    holes = []; L = s1 - s0; k = max(2, round(L / ZOC_PASO) + 1) if L > 30 else 1
    for i in range(k):
        sp = s0 + (L / 2 if k == 1 else 8 + (L - 16) * i / (k - 1)); base = a + d * sp
        if mode in ("L", "pared"):
            holes.append((Vector((base.x, base.y, und(base) + T + (ZOC_V - T) * 0.5)), Vector((nn.x, nn.y, 0))))
        if mode == "piso" or (mode == "L" and i < k - 1):
            off = 0.0 if mode == "piso" else (L - 16) / (k - 1) * 0.5
            q = a + d * (sp + off) - nn * 8.0
            holes.append((Vector((q.x, q.y, pz(pl, q))), pnorm(pl)))
    return bm, holes

# --- pestanas: remaches a la pared vecina
def pest_holes(tr, s):
    k = max(2, round(s["len"] / 60.0) + 1); out = []
    for i in range(k):
        t = (8 + (s["len"] - 16) * i / (k - 1)) / s["len"]
        p = s["a"] + (s["b"] - s["a"]) * t
        zf = s["A"].z + (s["B"].z - s["A"].z) * t; zt = s["At"].z + (s["Bt"].z - s["At"].z) * t
        out.append((Vector((p.x, p.y, zt - 4.5)), Vector((s["n"].x, s["n"].y, 0))))
    return out

# orden: bocas, esquineros, esquineros entre bandejas, zocalos
for nm, (b, lip, holes) in BOCA_PARTS.items():
    try_petg(f"PETG_Inox_Boca_{nm}", b, [], "boca", nm, egg_check=False, force=True)
    try_petg(f"PETG_Inox_Ceja_{nm}", lip, holes, "ceja", nm, egg_check=True, force=True)
def place_post(name, args, tray):
    """prueba variantes: ala normal, ala corta, levantado sobre el espacio de los huevos"""
    why = "forma imposible"
    for W, lift in ((POST_W, False), (10.0, False), (6.0, False), (POST_W, True), (10.0, True)):
        r = post(*args, W=W, lift_egg=lift)
        if not r: continue
        b_ = bvh_of(r[0]); why = hits(b_, egg=tray not in LOWER, petg=PETG_BVH, loc=tri_loc(r[0]))
        if try_petg(name, r[0], r[1], "esquinero", tray, quiet=True): return True
    if not (name.startswith("PETG_Inox_Union") and why == "forma imposible"):
        rep["petg"].setdefault("descartadas", []).append({"pieza": name, "con": why})
    return False
for nm, tr in TR.items():
    n = len(tr["poly"])
    for j in range(n):
        si, so = tr["segs"][j - 1], tr["segs"][j]
        if si and so and si["kind"] == "pared" and so["kind"] == "pared":
            V = tr["poly"][j]; place_post(f"PETG_Inox_Esquinero_{nm}_{j}", (V, si, tr, V, so, tr), nm)
    for s in tr["segs"]:
        if s and s["kind"] == "pest":
            for p, ax in pest_holes(tr, s): add_hole(p, ax, "pestana " + nm)
names = list(TR)
for x in range(len(names)):
    for y in range(x + 1, len(names)):
        tx, ty = TR[names[x]], TR[names[y]]
        for sA in tx["segs"]:
            if not sA or sA["kind"] != "pared": continue
            for sB in ty["segs"]:
                if not sB or sB["kind"] != "pared": continue
                for EA in (sA["a"], sA["b"]):
                    for EB in (sB["a"], sB["b"]):
                        if (EA - EB).length < 2.5:
                            place_post(f"PETG_Inox_Union_{names[x][7:]}_{names[y][7:]}_{sA['i']}_{sB['i']}",
                                       (EA, sA, tx, EB, sB, ty), names[x])
ZOC_PIEZA_MIN = 40.0
for nm, tr in TR.items():
    for s in tr["segs"]:
        if not s or s["kind"] != "pared" or s["len"] < ZOC_MIN: continue
        s0, end = ZOC_END, s["len"] - ZOC_END; k = 0
        n_max = max(1, math.ceil((end - s0) / ZOC_MAX)); full = (end - s0) / n_max
        while end - s0 >= ZOC_PIEZA_MIN:
            rem = end - s0
            lens = sorted({round(min(full, rem), 1), round(min(rem, 90.0), 1), round(min(rem, 60.0), 1), ZOC_PIEZA_MIN}, reverse=True)
            ok = False
            for L in lens:
                if L < ZOC_PIEZA_MIN or L > rem + 1e-6: continue
                for mode in ("L", "piso", "pared"):
                    bm, holes = zocalo(tr, s, s0, s0 + L, mode)
                    suf = {"L": "", "piso": "P", "pared": "V"}[mode]
                    if try_petg(f"PETG_Inox_Zocalo_{nm}_{s['i']}_{k+1}{suf}", bm, holes, "zocalo", nm, quiet=True):
                        ok = True; break
                if ok: break
            if ok: k += 1; s0 += L + 1.0
            else: s0 += 8.0

# ------------------------------------------------------------------ desarrollo plano (cara de los huevos)
class Iso:
    """isometria 3D (plano) -> 2D"""
    def __init__(s, O3, e1, e2, o2, x2, y2): s.O3, s.e1, s.e2, s.o2, s.x2, s.y2 = O3, e1, e2, o2, x2, y2
    def __call__(s, P): q = P - s.O3; return s.o2 + s.x2 * q.dot(s.e1) + s.y2 * q.dot(s.e2)

def unfold(tr):
    regs = tr["regs"]
    for r in regs: r["P3"] = [Vector((p.x, p.y, pz(r["pl"], p))) for p in r["poly"]]
    root = max(range(len(regs)), key=lambda i: abs(area2(regs[i]["poly"])))
    r = regs[root]; nrm = pnorm(r["pl"]); e1 = (r["P3"][1] - r["P3"][0]).normalized(); e2 = nrm.cross(e1)
    r["iso"] = Iso(r["P3"][0], e1, e2, Vector((0, 0)), Vector((1, 0)), Vector((0, 1)))
    done = {root}; tr["creases"] = []
    while len(done) < len(regs):
        prog = False
        for i in list(done):
            for j in range(len(regs)):
                if j in done: continue
                Pi, Pj = regs[i]["P3"], regs[j]["P3"]
                def on_b(q, P):
                    for k_ in range(len(P)):
                        a_, b_ = P[k_], P[(k_ + 1) % len(P)]; d_ = b_ - a_
                        t_ = max(0.0, min(1.0, (q - a_).dot(d_) / max(d_.length_squared, 1e-12)))
                        if (a_ + d_ * t_ - q).length < 0.05: return True
                    return False
                com = [q for q in Pj if on_b(q, Pi)] + [q for q in Pi if on_b(q, Pj)]
                com = [q for k_, q in enumerate(com) if all((q - r_).length > 0.05 for r_ in com[:k_])]
                if len(com) < 2 or max((q - com[0]).length for q in com) < 1.0: continue
                C0, C1 = com[0], max(com[1:], key=lambda q: (q - com[0]).length)
                u = (C1 - C0).normalized(); cj = sum(Pj, Vector()) / len(Pj)
                w = (cj - C0) - u * (cj - C0).dot(u); e2 = w.normalized()
                iso_i = regs[i]["iso"]; c0, c1 = iso_i(C0), iso_i(C1); x2 = (c1 - c0).normalized(); y2 = perp(x2)
                ci = sum((iso_i(p) for p in Pi), Vector((0, 0))) / len(Pi)
                if (ci - c0).dot(y2) > 0: y2 = -y2
                regs[j]["iso"] = Iso(C0, u, e2, c0, x2, y2)
                ang = math.degrees(pnorm(regs[i]["pl"]).angle(pnorm(regs[j]["pl"])))
                valle = pz(regs[i]["pl"], V2(cj)) < cj.z
                tr["creases"].append((c0, c1, ang if valle else -ang)); done.add(j); prog = True
        if not prog: aviso(f"{tr['name']}: region sin desplegar"); break
    n = len(tr["poly"])
    def m2(p2):
        ri = tr["region_of"](p2); pl = regs[ri]["pl"]; return regs[ri]["iso"](Vector((p2.x, p2.y, pz(pl, p2))))
    # puntos del contorno del piso
    v2 = []
    for i in range(n):
        p = tr["poly"][i]
        # un vertice de pliegue pertenece a dos regiones: usar la del tramo que llega (son iguales)
        s = tr["segs"][i]; sp = tr["segs"][i - 1]
        ri = s["reg"] if s else (sp["reg"] if sp else tr["region_of"](p))
        v2.append(regs[ri]["iso"](Vector((p.x, p.y, pz(regs[ri]["pl"], p)))))
    fl = [None] * n; faces = []
    for r in regs: faces.append({"P3": r["P3"], "iso": r["iso"], "nrm": pnorm(r["pl"])})
    for i in range(n):
        s = tr["segs"][i]
        if not s: continue
        reg = regs[s["reg"]]; iso_r = reg["iso"]
        A, B = s["A"], s["B"]; u = (B - A).normalized()
        w = (s["At"] - A) - u * (s["At"] - A).dot(u); e2 = w.normalized()
        a2, b2 = iso_r(A), iso_r(B); x2 = (b2 - a2).normalized(); y2 = perp(x2)
        cr = sum((iso_r(p) for p in reg["P3"]), Vector((0, 0))) / len(reg["P3"])
        if (cr - a2).dot(y2) > 0: y2 = -y2
        iso = Iso(A, u, e2, a2, x2, y2)
        # angulo interior piso-pared
        nf = pnorm(reg["pl"]); vin = nf.cross(u)
        if vin.dot(Vector((-s["n"].x, -s["n"].y, 0))) < 0: vin = -vin
        ang = math.degrees(math.acos(max(-1, min(1, vin.dot(e2)))))
        fl[i] = {"a2": a2, "b2": b2, "at2": iso(s["At"]), "bt2": iso(s["Bt"]), "iso": iso, "ang": ang, "kind": s["kind"]}
        faces.append({"P3": [A, B, s["Bt"], s["At"]], "iso": iso, "nrm": Vector((s["n"].x, s["n"].y, 0)).cross(Vector((0, 0, 0))) if False else None, "wall": s})
    # recortes en esquinas donde las alas se solapan
    def ang_cw(base, v):
        """angulo antihorario desde base (contorno CCW: desde el tramo que llega se gira hacia afuera)"""
        a = math.atan2(cross2(base, v), base.dot(v)); return a if a >= 0 else a + 2 * math.pi
    for j in range(n):
        f1, f2 = fl[j - 1], fl[j]
        if not f1 or not f2: continue
        Vv = v2[j]; ein = f1["a2"] - Vv
        r1, r2 = f1["bt2"] - Vv, f2["at2"] - Vv
        A1, A2 = ang_cw(ein, r1), ang_cw(ein, r2)
        if A2 < A1 - 1e-6:
            am = (A1 + A2) / 2; c, s_ = math.cos(am), math.sin(am)
            bis = Vector((ein.x * c - ein.y * s_, ein.x * s_ + ein.y * c)).normalized()
            p1 = line_x(Vv, bis, f1["at2"], f1["bt2"] - f1["at2"]); p2 = line_x(Vv, bis, f2["at2"], f2["bt2"] - f2["at2"])
            if p1: f1["bt2"] = p1
            if p2: f2["at2"] = p2
            f1["trim_end"] = True; f2["trim_start"] = True
    contour = []
    for i in range(n):
        contour.append(v2[i])
        if fl[i]: contour += [fl[i]["at2"], fl[i]["bt2"]]
    contour = [p for k, p in enumerate(contour) if (p - contour[k - 1]).length > 1e-3]
    # agujeros
    holes2 = []
    for p, ax, why in HOLES:
        for fc in faces:
            P3 = fc["P3"]; nrm = (P3[1] - P3[0]).cross(P3[2] - P3[0])
            if nrm.length < 1e-9: nrm = (P3[2] - P3[0]).cross(P3[3] - P3[0]) if len(P3) > 3 else nrm
            nrm = nrm.normalized(); den = ax.dot(nrm)
            if abs(den) < 0.3: continue
            t = (P3[0] - p).dot(nrm) / den
            if abs(t) > T + CL + T + 0.4: continue
            q = p + ax * t; q2 = fc["iso"](q); poly2 = [fc["iso"](x) for x in P3]
            if inside2(q2, poly2) and min((q2 - x).length for x in poly2) > 0.5:
                if all((q2 - h).length > 1.0 for h, _ in holes2): holes2.append((q2, why))
    # autointerseccion del contorno
    bad = 0; m = len(contour)
    for i in range(m):
        for k in range(i + 2, m):
            if i == 0 and k == m - 1: continue
            if seg_x(contour[i], contour[(i + 1) % m], contour[k], contour[(k + 1) % m]): bad += 1
    if bad: aviso(f"{tr['name']}: el desarrollo se solapa consigo mismo ({bad} cruces)")
    tr["flat"] = {"contour": contour, "fl": fl, "v2": v2, "holes": holes2}

for tr in TR.values(): unfold(tr)

# ------------------------------------------------------------------ DXF
LAYERS = [("CORTE_EXTERIOR", 7), ("CORTE_INTERIOR", 1), ("DOBLEZ", 5), ("TEXTO_NO_CORTAR", 3)]
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
    for lay, a, b in lines_: o += ["0", "LINE", "8", lay, "10", f(a.x), "20", f(a.y), "30", "0", "11", f(b.x), "21", f(b.y), "31", "0"]
    for lay, p, h, txt in texts: o += ["0", "TEXT", "8", lay, "10", f(p.x), "20", f(p.y), "30", "0", "40", f(h), "1", txt]
    o += ["0", "ENDSEC", "0", "EOF"]
    with open(path, "w", newline="\r\n") as fh: fh.write("\n".join(o) + "\n")
def circ(c, r, n=24): return [c + Vector((math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n))) * r for k in range(n)]

for nm, tr in TR.items():
    F = tr["flat"]; C = F["contour"]
    # orientar: lado mas largo del contorno horizontal, todo en el cuadrante positivo
    best = max(range(len(C)), key=lambda i: (C[(i + 1) % len(C)] - C[i]).length)
    d = (C[(best + 1) % len(C)] - C[best]).normalized(); R = Matrix(((d.x, d.y), (-d.y, d.x)))
    def tf(p): return R @ p
    pts = [tf(p) for p in C]; mn = Vector((min(p.x for p in pts), min(p.y for p in pts)))
    def T2(p): return tf(p) - mn
    polys = [("CORTE_EXTERIOR", [T2(p) for p in C])]
    polys += [("CORTE_INTERIOR", circ(T2(h), R_INOX)) for h, _ in F["holes"]]
    lines_, texts = [], []
    for f in F["fl"]:
        if not f: continue
        a, b = T2(f["a2"]), T2(f["b2"]); lines_.append(("DOBLEZ", a, b))
        mid = (a + b) / 2; texts.append(("TEXTO_NO_CORTAR", mid + Vector((1.5, 1.5)), 3.0,
                                         ("pestana " if f["kind"] == "pest" else "") + f"{f['ang']:.0f} deg"))
    for c0, c1, ang in tr["creases"]:
        a, b = T2(c0), T2(c1); lines_.append(("DOBLEZ", a, b))
        texts.append(("TEXTO_NO_CORTAR", (a + b) / 2 + Vector((1.5, -4)), 3.0,
                      f"pliegue {abs(ang):.0f} deg {'valle (hacia arriba)' if ang >= 0 else 'MONTE (hacia abajo)'}"))
    allp = [p for _, ps in polys for p in ps]
    W = max(p.x for p in allp); H = max(p.y for p in allp)
    c = sum((T2(p) for p in F["v2"]), Vector((0, 0))) / len(F["v2"])
    texts.append(("TEXTO_NO_CORTAR", c + Vector((-30, 16)), 5.0, f"{nm} inox 0.6"))
    texts.append(("TEXTO_NO_CORTAR", c + Vector((-30, 10)), 3.0, "cara de los huevos hacia arriba"))
    path = os.path.join(OUT_CNC, f"{nm}_{TAG}_desarrollo.dxf"); dxf(path, polys, lines_, texts)
    tr["flat"]["W"], tr["flat"]["H"] = W, H
    tr["flat"]["n_dob"] = sum(1 for f in F["fl"] if f) + len(tr["creases"])

# ------------------------------------------------------------------ objetos Blender
for o in bpy.data.objects:
    if o.name.startswith(("PVC_", "PETG_Zocalo", "PETG_Cuna", "PETG_Escuadras")):
        o.hide_set(True); o.hide_render = True
    if o.name.startswith(("INOX_", "PETG_Inox")): bpy.data.objects.remove(o)
def coll(name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in [x.name for x in bpy.context.scene.collection.children]: bpy.context.scene.collection.children.link(c)
    return c
def mat(name, col):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name); m.diffuse_color = col; return m
M_INOX = mat("Inox_Acero", (0.72, 0.75, 0.78, 1.0)); M_PETG = mat("PETG_Naranja", (0.95, 0.45, 0.1, 1.0))
def make_obj(c, name, bm, m, color):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.transform(Matrix.Scale(0.001, 4))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); c.objects.link(ob); me.materials.append(m); ob.color = color; return ob
def cut_holes(ob, holes, r=R_PETG):
    if not holes: return
    bm = bmesh.new()
    for p, ax in holes:
        Mx = Matrix.Translation(p * 0.001) @ ax.to_track_quat("Z", "Y").to_matrix().to_4x4()
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=20, radius1=r * 0.001, radius2=r * 0.001, depth=0.024, matrix=Mx)
    me = bpy.data.meshes.new("cut"); bm.to_mesh(me); bm.free()
    cu = bpy.data.objects.new("cut", me); bpy.context.scene.collection.objects.link(cu)
    md = ob.modifiers.new("h", "BOOLEAN"); md.operation = "DIFFERENCE"; md.object = cu
    try: md.solver = "MANIFOLD"
    except Exception: md.solver = "EXACT"
    d2 = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(d2)
    newme = bpy.data.meshes.new_from_object(ev); old = ob.data
    ob.modifiers.clear(); ob.data = newme; newme.materials.clear(); newme.materials.append(M_PETG)
    bpy.data.meshes.remove(old); bpy.data.objects.remove(cu); bpy.data.meshes.remove(me)
def union(ob, other_bm):
    me = bpy.data.meshes.new("u"); other_bm.transform(Matrix.Scale(0.001, 4)); other_bm.to_mesh(me); other_bm.free()
    cu = bpy.data.objects.new("u", me); bpy.context.scene.collection.objects.link(cu)
    md = ob.modifiers.new("u", "BOOLEAN"); md.operation = "UNION"; md.object = cu
    try: md.solver = "MANIFOLD"
    except Exception: md.solver = "EXACT"
    d2 = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(d2)
    newme = bpy.data.meshes.new_from_object(ev); old = ob.data
    ob.modifiers.clear(); ob.data = newme; newme.materials.clear(); newme.materials.append(M_PETG)
    bpy.data.meshes.remove(old); bpy.data.objects.remove(cu); bpy.data.meshes.remove(me)

C_INOX = coll("INOX_Bandejas")
for nm in TR:
    make_obj(C_INOX, f"INOX_{nm}", SHEET_BM[nm].copy(), M_INOX, (0.72, 0.75, 0.78, 1))
CP = {"boca": coll("PETG_Inox_Bocas"), "esquinero": coll("PETG_Inox_Esquineros"), "zocalo": coll("PETG_Inox_Zocalos")}
OBJ = {}
for p in PETG:
    if p["cat"] == "ceja": continue
    OBJ[p["name"]] = make_obj(CP[p["cat"]], p["name"], p["bm"], M_PETG, (0.95, 0.45, 0.1, 1))
for p in PETG:
    if p["cat"] != "ceja": continue
    bo = OBJ[p["name"].replace("_Ceja_", "_Boca_")]
    union(bo, p["bm"]); cut_holes(bo, p["holes"])
for p in PETG:
    if p["cat"] in ("esquinero", "zocalo"): cut_holes(OBJ[p["name"]], p["holes"])

# STL
lista = []
for ob in [o for o in bpy.data.objects if o.name.startswith("PETG_Inox")]:
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.wm.stl_export(filepath=os.path.join(OUT_STL, ob.name.replace("PETG_Inox_", "") + ".stl"), export_selected_objects=True, global_scale=1000.0)
    bm = bmesh.new(); bm.from_mesh(ob.data)
    closed = all(e.is_manifold for e in bm.edges); bm.free()
    dims = [round(v * 1000, 1) for v in ob.dimensions]
    lista.append((ob.name, dims, closed))

# ------------------------------------------------------------------ informe
n_riv = len(HOLES)
cat_n = {}
for p in PETG: cat_n[p["cat"]] = cat_n.get(p["cat"], 0) + 1
with open(os.path.join(OUT_STL, "Bandejas_inox_lista.txt"), "w", encoding="utf-8") as fh:
    fh.write("Bandejas inox 0.6 mm - piezas PETG (agujeros impresos D4.4 para remache 3 mm; en la chapa taladrar D3.2)\n\n")
    for nm, d, cl in lista: fh.write(f"{nm:<48} {d[0]:>6} x {d[1]:>6} x {d[2]:>6} mm   {'cerrada' if cl else 'REVISAR malla'}\n")
    fh.write(f"\nRemaches 3 mm (aprox.): {n_riv}\n")
    for nm, tr in TR.items():
        F = tr["flat"]
        fh.write(f"\n{nm}: desarrollo {F['W']:.0f} x {F['H']:.0f} mm, {F['n_dob']} dobleces, {len(F['holes'])} agujeros\n")
        for f in F["fl"]:
            if f: fh.write(f"   doblez {'pestana' if f['kind']=='pest' else 'pared  '}  {(f['b2']-f['a2']).length:6.1f} mm a {f['ang']:.0f} deg\n")
        for c0, c1, ang in tr["creases"]:
            fh.write(f"   pliegue del piso {(c1-c0).length:6.1f} mm  {abs(ang):.1f} deg {'valle' if ang >= 0 else 'MONTE (hacia abajo)'}\n")
for nm, tr in TR.items():
    F = tr["flat"]
    rep["bandejas"][nm] = {"desarrollo_mm": [round(F["W"]), round(F["H"])], "dobleces": F["n_dob"],
                           "paredes": sum(1 for s in tr["segs"] if s and s["kind"] == "pared"),
                           "pestanas": sum(1 for s in tr["segs"] if s and s["kind"] == "pest"),
                           "planos_piso": len(tr["regs"]), "agujeros": len(F["holes"]),
                           "desv_piso_mm": tr["dev"]}
rep["petg"]["cantidad"] = cat_n; rep["remaches"] = n_riv
rep["desv_detalle"] = {nm: tr["dev_all"] for nm, tr in TR.items()}
rep["mallas_abiertas"] = [nm for nm, d, cl in lista if not cl]
print("INFORME", json.dumps(rep, indent=1, default=str))
json.dump(rep, open(os.path.join(OUT_STL, "informe_bandejas_inox.json"), "w"), indent=1, default=str)
DBG = {}
for nm, tr in TR.items():
    L = lambda v: [round(x, 2) for x in v]
    DBG[nm] = {"poly": [L(p) for p in tr["poly"]], "kinds": tr["kinds"],
               "regs": [{"k": r["k"], "poly": [L(p) for p in r["poly"]]} for r in tr["regs"]],
               "segs": [None if not s_ else {k_: L(s_[k_]) for k_ in ("A", "B", "At", "Bt")} | {"kind": s_["kind"]} for s_ in tr["segs"]],
               "flat": {"contour": [L(p) for p in tr["flat"]["contour"]], "holes": [L(h) for h, _ in tr["flat"]["holes"]],
                        "folds": [[L(f["a2"]), L(f["b2"])] for f in tr["flat"]["fl"] if f] + [[L(a), L(b)] for a, b, _ in tr["creases"]]}}
json.dump(DBG, open(os.path.join(OUT_STL, "debug_bandejas_inox.json"), "w"))
if SAVE: bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
