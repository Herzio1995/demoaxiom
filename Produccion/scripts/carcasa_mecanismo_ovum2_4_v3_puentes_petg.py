"""
Ovum2_4_inox: CARCASA PROTECTORA del mecanismo (pesador + girador) con TAPA DE ACRILICO atornillada.  (v2)

v2 (pedido 2026-11-14): menos plastico, TODO el metal en UNA sola pieza plegada, caja recta sin voladizo.
(La v1 con marco de tubos PETG quedo en carcasa_mecanismo_ovum2_4_v1_tubos.py.)

  - ENVOLVENTE: una sola plancha de inox 0.6 que se envuelve en U alrededor del mecanismo:
        dobladillo - jamba izq - lateral izq - fondo - lateral der - jamba der - dobladillo
    Caras exteriores: x +-93, y -131 (fondo) .. -36 (frente), z 26.6 .. 210. Todos los dobleces a 90 hacia adentro.
      * pestanas superiores (12 mm) sobre las que apoya el acrilico; los laterales son duenos de las esquinas.
      * pestanas inferiores de los laterales (15 mm) apoyadas en el perfil 2020 con 4 M5 a tuerca T
        (largueros x +-85.8 en y -124, travesano en y -98).
      * fondo: arranca en z 34 (libra la PlacaPCB, z <= 32) con pestana de 10 mm; escotadura de la canaleta
        (x +-44, z >= 118) con sus bordes doblados hacia adentro (sin ribete plastico).
      * jambas desde z 74 (la placa BaseDelgadaMetal llega a x~58, z 61) con pestana inferior y dobladillo en el
        borde del vano. Vano central abierto (x +-48) para que el huevo salga hacia las bocas.
  - TAPA: acrilico 4 mm x +-93, y -131..-36 sobre las pestanas superiores, 10 tornillos M3 a tuercas remachables
    (rivnut M3, agujero 5 mm) en las pestanas.
  - PETG: marco FINO de 8 nodos de esquina + 10 puentes (4 verticales, 4 superiores que sujetan el acrilico,
    2 inferiores laterales). Todos con la misma seccion squircle R8 cuyo eje va 4 mm hacia adentro de la arista:
    por fuera queda una piel redondeada de ~4 mm que pasa al ras de nodo a puente (aspecto suave, sin escalones).
    Todos atornillados con M3 cabeza boton embutida al ras (los de arriba a las rivnut de la tapa).
    UNIONES ESTRUCTURALES (v3b): cada brazo de nodo termina en un MANGUITO (R10, extremos ahusados) que abraza
    12 mm del extremo del puente; un M3 de union a 20 mm de la esquina atraviesa manguito + puente + chapa (o
    acrilico + rivnut) -> nodos, puentes, chapa y tapa trabajan como un solo marco.
    Booleanas con el solver MANIFOLD (el EXACT dejaba bordes abiertos en los manguitos); "-- exact" vuelve al otro.

Salidas
  - Coleccion "Carcasa_Mecanismo".
  - Produccion/cnc/carcasa/Carcasa_Envolvente_INOX06_desarrollo.dxf (desarrollo plano con dobleces)
    y Carcasa_Tapa_ACRIL4.dxf
  - Produccion/stl/carcasa_mecanismo/*.stl + Carcasa_lista.txt
Uso:  blender -b Ovum2_4_inox.blend --python Produccion/scripts/carcasa_mecanismo_ovum2_4.py -- [nosave]
Plantillas: python Produccion/scripts/plantillas_pvc.py Produccion/cnc/carcasa "*_INOX06_*.dxf" carta
"""
import bpy, bmesh, sys, os, math, json, shutil, struct
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAVE = "nosave" not in argv
DEBUG = "debug" in argv
SOLVER = "EXACT" if "exact" in argv else "MANIFOLD"
ROOT = os.path.dirname(bpy.data.filepath)
OUT_STL = os.path.join(ROOT, "Produccion", "stl", "carcasa_mecanismo")
OUT_CNC = os.path.join(ROOT, "Produccion", "cnc", "carcasa")
for d in (OUT_STL, OUT_CNC):
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f.lower().endswith((".stl", ".dxf")): os.remove(os.path.join(d, f))
COL = "Carcasa_Mecanismo"
rep = {"avisos": []}
def aviso(s): rep["avisos"].append(s); print("AVISO:", s)

# ------------------------------------------------------------------ parametros (mm, caras exteriores)
XS, XJ = 93.0, 48.0          # lateral / borde del vano
YB, YF = -131.0, -36.0       # fondo / frente (jambas)
ZB = 26.6                    # base de los laterales (perfil 2020 en z 26.5)
ZBK = 34.0                   # base del fondo (PlacaPCB hasta z 32)
ZJ = 74.0                    # base de las jambas
ZT = 210.0                   # borde superior (cara de apoyo del acrilico = pestanas)
T = 0.6                      # inox
BD = 1.0                     # descuento por doblez a 90 (inox 0.6, radio ~ espesor)
W_TOP, W_BOT, W_BK, W_JB, W_DOB, W_NOT = 12.0, 15.0, 10.0, 10.0, 10.0, 8.0   # anchos de pestanas
NOTCH_X, NOTCH_Z = 44.0, 118.0
HOLG = 0.9                   # recorte de pestanas contra la cara interior de la pared vecina
RIVNUT_D, M3_D, M5_D = 5.0, 3.4, 5.5
T_ACR, RIVNUT_CAB = 4.0, 0.8
Z_ACR0 = ZT + RIVNUT_CAB; Z_ACR1 = Z_ACR0 + T_ACR      # el acrilico apoya en las cabezas de las rivnut
# marco PETG fino: nodos + puentes con la MISMA seccion squircle (radio R_P) cuyo eje va INS mm hacia adentro de
# la arista -> lo que queda fuera de la caja es una "piel" redondeada de ~4 mm que pasa suave de nodo a puente.
R_P, INS = 8.0, 4.0
J_NODO, GAP = 14.0, 0.3           # el nodo llega a 14 mm de la esquina; 0.3 mm de junta con el puente
# union estructural nodo-puente: cada brazo del nodo termina en un MANGUITO (casquillo) que abraza el extremo del
# puente a lo largo de LAP mm; un M3 atraviesa manguito + puente + chapa/acrilico y deja el marco trabado
LAP, R_MANG, R_MANG_FIN, R_HUECO = 12.0, 10.0, 9.0, R_P + 0.15
S_UNION = J_NODO + LAP / 2        # 20 mm: posicion de los tornillos de union desde la esquina
HOLG_PETG = 0.15
CAB_D, CAB_H = 6.2, 1.8           # M3 cabeza boton ISO 7380 (5.7 x 1.65) embutida al ras
X_LARGUERO, Y_TRAVESANO = 85.8, -98.0
M5_PTS = [(sx * X_LARGUERO, y) for sx in (-1, 1) for y in (-124.0, Y_TRAVESANO)]
# tornillos de la tapa (x, y); los 4 primeros pasan por los nodos de esquina
TAPA_PTS = [(sx * (XS - 6), y) for sx in (-1, 1) for y in (YB + 6, YF - 6)]
TAPA_PTS += [(sx * (XS - 6), y) for sx in (-1, 1) for y in (YB + S_UNION, -84.0, YF - S_UNION)]      # uniones + centro laterales
TAPA_PTS += [(sx * (XS - S_UNION), y) for sx in (-1, 1) for y in (YB + 6, YF - 6)]                  # uniones fondo / frente
# M3 horizontales por los laterales (sx, y, z): nodos inferiores, puentes verticales y puentes inferiores
# (el del fondo a z 33.5 se quito: su tuerca chocaba con la pestana inferior del fondo, z 34)
LAT_TORN = [(sx, YF - 6, 33.5) for sx in (-1, 1)]
LAT_TORN += [(sx, y, z) for sx in (-1, 1) for y in (YB + 6, YF - 6) for z in (ZB + S_UNION, 120.0, ZT + RIVNUT_CAB + T_ACR - S_UNION)]
LAT_TORN += [(sx, y, ZB + 6) for sx in (-1, 1) for y in (YB + S_UNION, YF - S_UNION)]

# ------------------------------------------------------------------ desarrollo plano (u a lo largo de la envoltura, v = z)
def flat(w, nb): return w - BD / 2 * nb
a = [0.0]
for w, nb in ((W_DOB, 1), (XS - XJ, 2), (YF - YB, 2), (2 * XS, 2), (YF - YB, 2), (XS - XJ, 2), (W_DOB, 1)):
    a.append(a[-1] + flat(w, nb))
A1, A2, A3, A4, A5, A6, A7 = a[1:]
UMAX = A7
def vz(z): return z + BD / 2 if z < (ZT - 1) else z - BD / 2   # (solo para lineas de doblez)
V_SB, V_BK, V_JB, V_T = ZB + BD / 2, ZBK + BD / 2, ZJ + BD / 2, ZT - BD / 2
V_SB0 = V_SB - flat(W_BOT, 1); V_BK0 = V_BK - flat(W_BK, 1); V_JB0 = V_JB - flat(W_JB, 1); V_T1 = V_T + flat(W_TOP, 1)
V_DOB0, V_DOB1 = V_JB + W_JB, V_T - W_TOP
# mapeo mundo <-> u en cada pared
def u_de(pared, q):
    if pared == "JL": return A1 + (-XJ - q) * (A2 - A1) / (XS - XJ)
    if pared == "SL": return A2 + (YF - q) * (A3 - A2) / (YF - YB)
    if pared == "B":  return A3 + (q + XS) * (A4 - A3) / (2 * XS)
    if pared == "SR": return A4 + (q - YB) * (A5 - A4) / (YF - YB)
    if pared == "JR": return A5 + (XS - q) * (A6 - A5) / (XS - XJ)
UN0, UN1 = u_de("B", -NOTCH_X), u_de("B", NOTCH_X)
WN = flat(W_NOT, 1)
RECTS = []
def R_(u0, u1, v0, v1): RECTS.append((min(u0, u1), max(u0, u1), v0, v1))
def espejo(u): return UMAX - u
for m in (False, True):
    f = (lambda u: espejo(u)) if m else (lambda u: u)
    R_(f(0), f(A1), V_DOB0, V_DOB1)                                   # dobladillo del vano
    R_(f(A1), f(A2), V_JB, V_T)                                       # jamba
    R_(f(A1), f(A2 - flat(W_TOP, 1) - 0.5), V_T, V_T1)                # pestana sup jamba (el lateral es dueno)
    R_(f(A1), f(A2 - HOLG), V_JB0, V_JB)                              # pestana inf jamba
    R_(f(A2), f(A3), V_SB, V_T)                                       # lateral
    R_(f(A2 + HOLG), f(A3 - HOLG), V_T, V_T1)                         # pestana sup lateral
    R_(f(A2), f(A3), V_SB0, V_SB)                                     # pestana inf lateral (M5)
    R_(f(A3), f(UN0), NOTCH_Z, V_T)                                   # fondo, lado de la escotadura
    R_(f(UN0), f(UN0 + WN), NOTCH_Z + WN, V_T)                        # pestana vertical de la escotadura
    R_(f(A3 + flat(W_TOP, 1) + 0.5), f(UN0 - HOLG), V_T, V_T1)        # pestana sup del fondo
R_(A3, A4, V_BK, NOTCH_Z)                                             # fondo, parte baja
R_(UN0 + WN + 0.5, UN1 - WN - 0.5, NOTCH_Z, NOTCH_Z + WN)            # pestana inferior de la escotadura (alivio 0.5)
R_(A3 + HOLG, A4 - HOLG, V_BK0, V_BK)                                 # pestana inferior del fondo

DOBLECES = []   # (u0, v0, u1, v1, texto)
for m in (False, True):
    f = (lambda u: espejo(u)) if m else (lambda u: u)
    DOBLECES += [(f(A1), V_DOB0, f(A1), V_DOB1, "90"), (f(A2), V_JB, f(A2), V_T, "90"), (f(A3), V_BK, f(A3), V_T, "90"),
                 (f(A1), V_T, f(A2 - flat(W_TOP, 1) - 0.5), V_T, "90"), (f(A1), V_JB, f(A2 - HOLG), V_JB, "90"),
                 (f(A2 + HOLG), V_T, f(A3 - HOLG), V_T, "90"), (f(A2), V_SB, f(A3), V_SB, "90"),
                 (f(UN0), NOTCH_Z + WN, f(UN0), V_T, "90"),
                 (f(A3 + flat(W_TOP, 1) + 0.5), V_T, f(UN0 - HOLG), V_T, "90")]
DOBLECES += [(UN0 + WN + 0.5, NOTCH_Z, UN1 - WN - 0.5, NOTCH_Z, "90"), (A3 + HOLG, V_BK, A4 - HOLG, V_BK, "90")]
# la pestana inferior de la escotadura esta DENTRO del hueco: v NOTCH_Z..NOTCH_Z+WN, se dobla en v = NOTCH_Z

# agujeros en el plano (u, v, diametro, que)
AG = []
def v_pest_sup(x_o_y_dist): return V_T + (x_o_y_dist - BD / 2)
for x, y in TAPA_PTS:
    if abs(abs(x) - (XS - 6)) < 0.1:      # pestana lateral
        u = u_de("SL" if x < 0 else "SR", y); AG.append((u, v_pest_sup(XS - abs(x)), RIVNUT_D, "rivnut"))
    elif abs(y - (YB + 6)) < 0.1:
        AG.append((u_de("B", x), v_pest_sup(y - YB), RIVNUT_D, "rivnut"))
    else:
        AG.append((u_de("JL" if x < 0 else "JR", x), v_pest_sup(YF - y), RIVNUT_D, "rivnut"))
for x, y in M5_PTS:
    AG.append((u_de("SL" if x < 0 else "SR", y), V_SB - ((XS - abs(x)) - BD / 2), M5_D, "M5"))
for sx, y, z in LAT_TORN:
    AG.append((u_de("SL" if sx < 0 else "SR", y), z + BD / 2, M3_D, "M3"))

# ------------------------------------------------------------------ contorno = union de rectangulos (grilla)
def contorno(rects):
    us = sorted({r[0] for r in rects} | {r[1] for r in rects}); vs = sorted({r[2] for r in rects} | {r[3] for r in rects})
    def lleno(i, j):
        cu, cv = (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2
        return any(r[0] < cu < r[1] and r[2] < cv < r[3] for r in rects)
    F = {(i, j) for i in range(len(us) - 1) for j in range(len(vs) - 1) if lleno(i, j)}
    E = {}
    for i, j in F:   # aristas orientadas CCW del borde
        if (i, j - 1) not in F: E[(i, j)] = (i + 1, j)
        if (i + 1, j) not in F: E[(i + 1, j)] = (i + 1, j + 1)
        if (i, j + 1) not in F: E[(i + 1, j + 1)] = (i, j + 1)
        if (i - 1, j) not in F: E[(i, j + 1)] = (i, j)
    loops = []
    while E:
        s = next(iter(E)); lp = [s]; c = E.pop(s)
        while c != s: lp.append(c); c = E.pop(c)
        pts = [(us[i], vs[j]) for i, j in lp]
        out = []   # quitar colineales
        for k in range(len(pts)):
            p0, p1, p2 = pts[k - 1], pts[k], pts[(k + 1) % len(pts)]
            if abs((p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0])) > 1e-9: out.append(p1)
        loops.append(out)
    return loops
LOOPS = contorno(RECTS)
if len(LOOPS) != 1: aviso(f"el desarrollo tiene {len(LOOPS)} contornos (deberia ser 1)")

# ------------------------------------------------------------------ primitivas 3D
def box(bm, mn, mx):
    g = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=g["verts"], vec=[mx[i] - mn[i] for i in range(3)])
    bmesh.ops.translate(bm, verts=g["verts"], vec=[(mx[i] + mn[i]) / 2 for i in range(3)])
def B(bm, x0, x1, y0, y1, z0, z1): box(bm, (min(x0, x1), min(y0, y1), min(z0, z1)), (max(x0, x1), max(y0, y1), max(z0, z1)))
def cyl(bm, c, ax, r, L, seg=24):
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=L)
    bmesh.ops.rotate(bm, verts=g["verts"], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(Vector(ax)).to_matrix())
    bmesh.ops.translate(bm, verts=g["verts"], vec=Vector(c))
def superelipsoide(bm, c, r):
    g = bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=1.0)
    for v in g["verts"]:
        d = v.co.copy(); s = (abs(d.x) ** 4 + abs(d.y) ** 4 + abs(d.z) ** 4) ** 0.25
        v.co = Vector(c) + d / s * r

col = bpy.data.collections.get(COL)
if col is None:
    col = bpy.data.collections.new(COL); bpy.context.scene.collection.children.link(col)
for ob in list(col.objects): bpy.data.objects.remove(ob, do_unlink=True)
tmp = bpy.data.collections.new("_tmp_carcasa"); bpy.context.scene.collection.children.link(tmp)
def bm_obj(name, bm, c=tmp):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bmesh.ops.scale(bm, verts=bm.verts, vec=(0.001,) * 3)
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new(name, me); c.objects.link(ob); return ob
def aplicar(ob, operand, op):
    m = ob.modifiers.new("b", "BOOLEAN"); m.operation = op; m.solver = SOLVER; m.object = operand; m.use_self = True
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    ob.modifiers.clear(); old = ob.data; ob.data = me; bpy.data.meshes.remove(old)
    if DEBUG:
        bm_ = bmesh.new(); bm_.from_mesh(ob.data); nm_ = sum(1 for e in bm_.edges if not e.is_manifold); bm_.free()
        if nm_: print("DBG", ob.name, op, operand.name, nm_)
def borrar(ob): bpy.data.objects.remove(ob, do_unlink=True)
def mat(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name); m.diffuse_color = rgba
    try:
        if rgba[3] < 1: m.surface_render_method = "BLENDED"
    except Exception: pass
    return m
M_PETG = mat("PETG_Gris_Oscuro", (0.10, 0.11, 0.12, 1.0))
M_INOX = mat("Inox_Acero", (0.72, 0.75, 0.78, 1.0))
M_ACR = mat("Acrilico_Transparente", (0.75, 0.88, 0.95, 0.25))
def finalizar(ob, m):
    ob.data.materials.clear(); ob.data.materials.append(m); ob.color = m.diffuse_color
    tmp.objects.unlink(ob); col.objects.link(ob)

# ------------------------------------------------------------------ envolvente 3D (plegada)
bm = bmesh.new(); i = T
for sx in (-1, 1):
    B(bm, sx * XS, sx * (XS - i), YB, YF, ZB, ZT)                                        # lateral
    B(bm, sx * (XS - i), sx * (XS - W_TOP), YB + i + 0.3, YF - i - 0.3, ZT - i, ZT)       # pestana sup lateral
    B(bm, sx * (XS - i), sx * (XS - W_BOT), YB + i, YF, ZB, ZB + i)                       # pestana inf lateral
    B(bm, sx * XJ, sx * (XS - i + 0.01), YF, YF - i, ZJ, ZT)                              # jamba
    B(bm, sx * XJ, sx * (XS - W_TOP - 0.5), YF - i, YF - W_TOP, ZT - i, ZT)               # pestana sup jamba
    B(bm, sx * XJ, sx * (XS - i - 0.3), YF - i, YF - W_JB, ZJ, ZJ + i)                    # pestana inf jamba
    B(bm, sx * XJ, sx * (XJ + i), YF - i, YF - W_DOB, ZJ + W_JB, ZT - W_TOP)              # dobladillo del vano
    B(bm, sx * (XS - i + 0.01), sx * NOTCH_X, YB, YB + i, ZBK, ZT)                        # fondo (lado)
    B(bm, sx * NOTCH_X, sx * (NOTCH_X - i), YB + i, YB + W_NOT, NOTCH_Z + W_NOT, ZT)      # pestana vert escotadura
    B(bm, sx * (XS - W_TOP - 0.5), sx * (NOTCH_X + HOLG), YB + i, YB + W_TOP, ZT - i, ZT) # pestana sup fondo
B(bm, -XS + i - 0.01, XS - i + 0.01, YB, YB + i, ZBK, NOTCH_Z)                            # fondo (bajo)
B(bm, -(NOTCH_X - W_NOT), NOTCH_X - W_NOT, YB + i, YB + W_NOT, NOTCH_Z, NOTCH_Z + i)      # pestana inf escotadura
B(bm, -(XS - i - 0.3), XS - i - 0.3, YB + i, YB + W_BK, ZBK, ZBK + i)                     # pestana inf fondo
env = bm_obj("INOX_Carcasa_Envolvente", bm)
hb = bmesh.new()
for x, y in TAPA_PTS: cyl(hb, (x, y, ZT), (0, 0, 1), RIVNUT_D / 2, 4)
for x, y in M5_PTS: cyl(hb, (x, y, ZB), (0, 0, 1), M5_D / 2, 4)
for sx, y, z in LAT_TORN: cyl(hb, (sx * XS, y, z), (1, 0, 0), M3_D / 2, 4)
ho = bm_obj("_ag", hb); aplicar(env, ho, "DIFFERENCE"); borrar(ho); finalizar(env, M_INOX)

# ------------------------------------------------------------------ tapa de acrilico
def rect_redondeado(x0, x1, y0, y1, r, n=6):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            t = math.radians(a0 + 90 * k / n); pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts
ACR_POLY = rect_redondeado(-XS, XS, YB, YF, 3.0)
bm = bmesh.new()
v0 = [bm.verts.new((x, y, Z_ACR0)) for x, y in ACR_POLY]; v1 = [bm.verts.new((x, y, Z_ACR1)) for x, y in ACR_POLY]
n = len(v0); bm.faces.new(v0[::-1]); bm.faces.new(v1)
for k in range(n): bm.faces.new((v0[k], v0[(k + 1) % n], v1[(k + 1) % n], v1[k]))
acr = bm_obj("ACRILICO_Carcasa_Tapa", bm)
hb = bmesh.new()
for x, y in TAPA_PTS: cyl(hb, (x, y, (Z_ACR0 + Z_ACR1) / 2), (0, 0, 1), M3_D / 2, 10)
ho = bm_obj("_ag", hb); aplicar(acr, ho, "DIFFERENCE"); borrar(ho); finalizar(acr, M_ACR)

# ------------------------------------------------------------------ marco PETG fino: nodos + puentes
def squircle(r, n=48):
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n; c, s_ = math.cos(t), math.sin(t)
        out.append((r * math.copysign(abs(c) ** 0.5, c), r * math.copysign(abs(s_) ** 0.5, s_)))
    return out
def sq_prism(bm, c0, c1, r):
    c0, c1 = Vector(c0), Vector(c1); k = max(range(3), key=lambda q: abs(c1[q] - c0[q])); u, w = [q for q in range(3) if q != k]
    rings = []
    for c in (c0, c1):
        ring = []
        for a_, b_ in squircle(r):
            p = c.copy(); p[u] += a_; p[w] += b_; ring.append(bm.verts.new(p))
        rings.append(ring)
    n = len(rings[0]); bm.faces.new(rings[0][::-1]); bm.faces.new(rings[1])
    for q in range(n): bm.faces.new((rings[0][q], rings[0][(q + 1) % n], rings[1][(q + 1) % n], rings[1][q]))
# tornillos que tocan el marco: (punto en la cara de la chapa/acrilico, normal exterior)
def _u(*ds): return any(abs(d - S_UNION) < 0.5 for d in ds)      # tornillo de union (a S_UNION de una esquina)
TORN_MARCO = [(Vector((x, y, Z_ACR1)), Vector((0, 0, 1)), _u(XS - abs(x), y - YB, YF - y)) for x, y in TAPA_PTS]
TORN_MARCO += [(Vector((sx * XS, y, z)), Vector((sx, 0, 0)), _u(z - ZB, Z_ACR1 - z, y - YB, YF - y)) for sx, y, z in LAT_TORN]
CAB_H_UNION = 0.8                    # en los manguitos la cabeza queda 0.85 mm saliente y aprieta el casquillo
ZK = Z_ACR1 - INS                    # eje de los puentes superiores
ZI = ZB + INS                        # eje de los puentes inferiores
def ejex(sx): return sx * (XS - INS)
def ejey(yc, sy): return yc - sy * INS
MARCO = []
def loft(bm, C, k, d, anillos):
    """tubo squircle a lo largo del eje k (sentido d) desde C: anillos = [(dist desde C, radio)], con tapas"""
    u, w = [q for q in range(3) if q != k]; rings = []
    for s, r in anillos:
        c = Vector(C); c[k] += d * s; ring = []
        for a_, b_ in squircle(r):
            p = c.copy(); p[u] += a_; p[w] += b_; ring.append(bm.verts.new(p))
        rings.append(ring)
    n = len(rings[0]); bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    for i in range(len(rings) - 1):
        for q in range(n): bm.faces.new((rings[i][q], rings[i][(q + 1) % n], rings[i + 1][(q + 1) % n], rings[i + 1][q]))
def brazo(C, k, d):
    """brazo del nodo con manguito: (shell, hueco). C = centro del nodo (a INS de la esquina)"""
    s0 = J_NODO - INS                                # distancia desde C hasta la junta
    an = [(0.0, R_P), (s0 - 3.0, R_P), (s0, R_MANG), (s0 + LAP - 2.5, R_MANG), (s0 + LAP, R_MANG_FIN)]
    c0 = Vector(C); c0[k] += d * s0; c1 = Vector(C); c1[k] += d * (s0 + LAP + 1)
    return (lambda bm: loft(bm, C, k, d, an)), (c0, c1)
def pieza_marco(nombre, shells, huecos=()):
    """shells: funciones bm->None; se unen, se resta la caja (+ holgura), los huecos de los manguitos y los tornillos"""
    bm = bmesh.new(); shells[0](bm); ob = bm_obj(nombre, bm)
    for f in shells[1:]:                         # de a UNA: formas solapadas en un mismo operando dejan caras internas
        bm = bmesh.new(); f(bm)
        uo = bm_obj("_u", bm); aplicar(ob, uo, "UNION"); borrar(uo)
    vs = [v.co * 1000 for v in ob.data.vertices]
    lo = Vector([min(v[q] for v in vs) for q in range(3)]); hi = Vector([max(v[q] for v in vs) for q in range(3)])
    bm = bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.scale(bm, verts=bm.verts, vec=(1000,) * 3); tree = BVHTree.FromBMesh(bm); bm.free()
    cb = bmesh.new(); h = HOLG_PETG
    B(cb, -300, 300, -400, 200, -100, ZB)                              # nada por debajo de la base
    co = bm_obj("_c", cb); aplicar(ob, co, "DIFFERENCE"); borrar(co)
    cb = bmesh.new()
    B(cb, -XS - h, XS + h, YB - h, YF + h, -100, Z_ACR1 + h)          # la caja + el acrilico
    co = bm_obj("_c", cb); aplicar(ob, co, "DIFFERENCE"); borrar(co)
    # Cortadores en GRUPOS separados y sin solapes dentro de cada grupo: con MANIFOLD, dos solidos del mismo cortador
    # que se solapan (agujero dentro del avellanado o del hueco del manguito) dejaban un "tapon" flotante en el agujero.
    g_huecos, g_ag, g_cab = bmesh.new(), bmesh.new(), bmesh.new()
    for c0, c1 in huecos: sq_prism(g_huecos, c0, c1, R_HUECO)          # alojamiento del extremo del puente
    n_t = 0
    es_nodo = bool(huecos)
    for p, nrm, union in TORN_MARCO:
        if not all(lo[q] - 1 < p[q] < hi[q] + 1 for q in range(3)): continue
        hit = tree.ray_cast(p + nrm * 30, -nrm)
        if hit[0] is None: continue
        sup = hit[0]; n_t += 1
        cyl(g_ag, p + nrm * 11.0, nrm, M3_D / 2, 24)                     # de 1 mm dentro de la caja hasta 23 mm fuera
        if union and not es_nodo: continue                               # bajo el manguito: solo el agujero
        prof = CAB_H_UNION if union else CAB_H                           # en el manguito la cabeza aprieta el casquillo
        cyl(g_cab, sup - nrm * prof + nrm * 10, nrm, CAB_D / 2, 20)
        esp = (sup - p).dot(nrm) - prof
        if esp < 2.0: aviso(f"{nombre}: queda {esp:.1f} mm bajo la cabeza")
    for g in (g_huecos, g_ag, g_cab):
        if not g.verts: g.free(); continue
        co = bm_obj("_c", g); aplicar(ob, co, "DIFFERENCE"); borrar(co)
    limpiar(ob, nombre); finalizar(ob, M_PETG)
    MARCO.append((ob, n_t)); return ob
def limpiar(ob, nombre):
    """une vertices duplicados, disuelve caras/aristas degeneradas, borra restos sueltos y deja normales hacia fuera"""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    # (sin remove_doubles: soldar vertices cercanos crea aristas de 4 caras donde dos superficies se rozan)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.000001)                 # 0.001 mm
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # componentes conexas: se queda solo la mayor (cualquier otra es un resto de booleana)
    resto, comps = set(bm.faces), []
    while resto:
        f0 = resto.pop(); pila = [f0]; c = {f0}
        while pila:
            f = pila.pop()
            for e in f.edges:
                for g in e.link_faces:
                    if g in resto: resto.discard(g); c.add(g); pila.append(g)
        comps.append(c)
    comps.sort(key=len, reverse=True)
    if DEBUG:
        for c in comps:
            vs = [v.co * 1000 for f in c for v in f.verts]
            print("DBGC", nombre, len(c), [round(min(v[q] for v in vs), 2) for q in range(3)], [round(max(v[q] for v in vs), 2) for q in range(3)])
        print("DBGN", nombre, [(tuple(round(c_ * 1000, 2) for c_ in e.verts[0].co), len(e.link_faces)) for e in bm.edges if not e.is_manifold][:6])
    if len(comps) > 1:
        print(f"limpieza {nombre}: {len(comps) - 1} astilla(s) de booleana eliminada(s)")
        bmesh.ops.delete(bm, geom=[f for c in comps[1:] for f in c], context="FACES")
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context="EDGES")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    if nm: aviso(f"{nombre}: {nm} aristas no-manifold tras limpiar")
    if bm.calc_volume(signed=True) < 0: bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(ob.data); bm.free(); ob.data.update()
L_ = lambda sx: "Izq" if sx < 0 else "Der"
for sx in (-1, 1):
    for sy, yc, nom in ((-1, YB, "Fondo"), (1, YF, "Frente")):
        X, Y = ejex(sx), ejey(yc, sy)
        bz = [brazo((X, Y, ZK), 0, -sx), brazo((X, Y, ZK), 1, -sy), brazo((X, Y, ZK), 2, -1)]
        pieza_marco(f"PETG_Carcasa_Nodo_Sup_{nom}_{L_(sx)}",
                    [lambda bm, X=X, Y=Y: superelipsoide(bm, (X, Y, ZK), R_P)] + [b[0] for b in bz], [b[1] for b in bz])
        bz = [brazo((X, Y, ZI), 1, -sy), brazo((X, Y, ZI), 2, 1)]
        pieza_marco(f"PETG_Carcasa_Nodo_Inf_{nom}_{L_(sx)}",
                    [lambda bm, X=X, Y=Y: superelipsoide(bm, (X, Y, ZI), R_P)] + [b[0] for b in bz], [b[1] for b in bz])
        pieza_marco(f"PETG_Carcasa_Puente_Vertical_{nom}_{L_(sx)}", [
            lambda bm, X=X, Y=Y: sq_prism(bm, (X, Y, ZB + J_NODO + GAP), (X, Y, Z_ACR1 - J_NODO - GAP), R_P)])
    X = ejex(sx)
    pieza_marco(f"PETG_Carcasa_Puente_Sup_Lateral_{L_(sx)}", [
        lambda bm, X=X: sq_prism(bm, (X, YB + J_NODO + GAP, ZK), (X, YF - J_NODO - GAP, ZK), R_P)])
    pieza_marco(f"PETG_Carcasa_Puente_Inf_Lateral_{L_(sx)}", [
        lambda bm, X=X: sq_prism(bm, (X, YB + J_NODO + GAP, ZI), (X, YF - J_NODO - GAP, ZI), R_P)])
for sy, yc, nom in ((-1, YB, "Fondo"), (1, YF, "Frente")):
    Y = ejey(yc, sy)
    pieza_marco(f"PETG_Carcasa_Puente_Sup_{nom}", [
        lambda bm, Y=Y: sq_prism(bm, (-XS + J_NODO + GAP, Y, ZK), (XS - J_NODO - GAP, Y, ZK), R_P)])
NODOS = [m[0] for m in MARCO]
rep["tornillos_marco"] = sum(m[1] for m in MARCO)

# ------------------------------------------------------------------ interferencias
def bvh_world(ob):
    dg = bpy.context.evaluated_depsgraph_get(); oe = ob.evaluated_get(dg); me = oe.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); bm.transform(ob.matrix_world); oe.to_mesh_clear()
    t = BVHTree.FromBMesh(bm); bm.free(); return t
otros = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get() and not o.hide_render
         and not any(c.name in (COL, tmp.name) for c in o.users_collection)]
bv = [(o, bvh_world(o)) for o in otros]
choques = []
for ob in [env, acr] + NODOS:
    t = bvh_world(ob)
    for o, to in bv:
        if t.overlap(to): choques.append((ob.name, o.name))
for x, y in choques: aviso(f"interferencia {x} <-> {y}")
rep["interferencias"] = choques

# ------------------------------------------------------------------ DXF / STL / lista
LAYERS = [("CORTE_EXTERIOR", 7), ("CORTE_INTERIOR", 1), ("DOBLEZ", 5), ("TEXTO_NO_CORTAR", 3)]
def dxf(path, polys, lines_, texts):
    o = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
         "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(LAYERS))]
    for nm, cl in LAYERS: o += ["0", "LAYER", "2", nm, "70", "0", "62", str(cl), "6", "CONTINUOUS"]
    o += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    f = lambda v: "%.4f" % v
    for lay, pts in polys:
        o += ["0", "POLYLINE", "8", lay, "66", "1", "70", "1", "10", "0", "20", "0", "30", "0"]
        for x, y in pts: o += ["0", "VERTEX", "8", lay, "10", f(x), "20", f(y), "30", "0"]
        o += ["0", "SEQEND", "8", lay]
    for lay, p, q in lines_: o += ["0", "LINE", "8", lay, "10", f(p[0]), "20", f(p[1]), "30", "0", "11", f(q[0]), "21", f(q[1]), "31", "0"]
    for lay, (x, y), h, txt in texts: o += ["0", "TEXT", "8", lay, "10", f(x), "20", f(y), "30", "0", "40", f(h), "1", txt]
    o += ["0", "ENDSEC", "0", "EOF"]
    with open(path, "w", newline="\r\n") as fh: fh.write("\n".join(o) + "\n")
def circ2(c, d, n=24): return [(c[0] + d / 2 * math.cos(2 * math.pi * k / n), c[1] + d / 2 * math.sin(2 * math.pi * k / n)) for k in range(n)]
v_min = min(p[1] for lp in LOOPS for p in lp)
S = lambda p: (p[0], p[1] - v_min)
polys = [("CORTE_EXTERIOR", [S(p) for p in lp]) for lp in LOOPS] + [("CORTE_INTERIOR", circ2(S((u, v)), d)) for u, v, d, _ in AG]
lines_ = [("DOBLEZ", S((u0, v0)), S((u1, v1))) for u0, v0, u1, v1, _ in DOBLECES]
texts = [("TEXTO_NO_CORTAR", S((A3 + 30, 150)), 6.0, "Carcasa envolvente - inox 0.6 - UNA pieza"),
         ("TEXTO_NO_CORTAR", S((A3 + 30, 141)), 3.5, "cara EXTERIOR hacia abajo: TODOS los dobleces 90 hacia arriba"),
         ("TEXTO_NO_CORTAR", S((A3 + 30, 135)), 3.5, "orden: pestanas -> escotadura -> dobladillos -> 4 esquinas verticales"),
         ("TEXTO_NO_CORTAR", S((A3 + 30, 129)), 3.5, "agujeros: 5.0 rivnut M3 / 5.5 M5 / 3.4 M3"),
         ("TEXTO_NO_CORTAR", S(((A2 + A3) / 2 - 20, 120)), 5.0, "LATERAL IZQ"), ("TEXTO_NO_CORTAR", S(((A4 + A5) / 2 - 20, 120)), 5.0, "LATERAL DER"),
         ("TEXTO_NO_CORTAR", S(((A1 + A2) / 2 - 12, 150)), 4.0, "JAMBA"), ("TEXTO_NO_CORTAR", S(((A5 + A6) / 2 - 12, 150)), 4.0, "JAMBA"),
         ("TEXTO_NO_CORTAR", S((A3 + 30, 80)), 5.0, "FONDO")]
dxf(os.path.join(OUT_CNC, "Carcasa_Envolvente_INOX06_desarrollo.dxf"), polys, lines_, texts)
W_FLAT = UMAX; H_FLAT = max(p[1] for lp in LOOPS for p in lp) - v_min
x0, y0 = -XS, YB
dxf(os.path.join(OUT_CNC, "Carcasa_Tapa_ACRIL4.dxf"),
    [("CORTE_EXTERIOR", [(x - x0, y - y0) for x, y in ACR_POLY])] + [("CORTE_INTERIOR", circ2((x - x0, y - y0), M3_D)) for x, y in TAPA_PTS],
    [], [("TEXTO_NO_CORTAR", (60, 50), 5.0, "Tapa acrilico 4 mm"), ("TEXTO_NO_CORTAR", (60, 43), 3.0, "lado del canal (fondo) abajo")])
def cara_abajo(nombre):
    """direccion (en coordenadas de montaje) que queda apoyada en la cama de impresion"""
    if "_Inf" in nombre: return Vector((0, 0, -1))                     # base plana cortada en ZB
    if "_Sup" in nombre: return Vector((0, 0, 1))                      # boca abajo: cara exterior superior en la cama
    return Vector((1 if nombre.endswith("_Der") else -1, 0, 0))        # puentes verticales: acostados sobre su cara lateral exterior
def export_stl(ob, path, imprimir=True):
    """STL en mm. imprimir=True: orientado para la cama (apoyado en z=0, centrado en x/y, eje largo segun X)"""
    me = ob.data; me.calc_loop_triangles(); W = ob.matrix_world
    pts = [W @ v.co * 1000 for v in me.vertices]
    if imprimir:
        R = cara_abajo(ob.name).rotation_difference(Vector((0, 0, -1))).to_matrix()
        pts = [R @ p for p in pts]
        dx = max(p.x for p in pts) - min(p.x for p in pts); dy = max(p.y for p in pts) - min(p.y for p in pts)
        if dy > dx: pts = [Vector((p.y, -p.x, p.z)) for p in pts]
        c = Vector(((max(p.x for p in pts) + min(p.x for p in pts)) / 2, (max(p.y for p in pts) + min(p.y for p in pts)) / 2, min(p.z for p in pts)))
        pts = [p - c for p in pts]
    with open(path, "wb") as fh:
        fh.write(b"carcasa_mecanismo_ovum2_4".ljust(80, b" ")); fh.write(struct.pack("<I", len(me.loop_triangles)))
        for lt in me.loop_triangles:
            vs = [pts[k] for k in lt.vertices]
            fh.write(struct.pack("<3f", *(vs[1] - vs[0]).cross(vs[2] - vs[0]).normalized()))
            for v in vs: fh.write(struct.pack("<3f", *v))
            fh.write(b"\0\0")
    return [round(max(p[q] for p in pts) - min(p[q] for p in pts), 1) for q in range(3)]
vol_petg = 0.0
OUT_STL_MONT = os.path.join(OUT_STL, "montaje"); os.makedirs(OUT_STL_MONT, exist_ok=True)
for f in os.listdir(OUT_STL):                                          # borra STL viejos (posicion de montaje)
    if f.lower().endswith(".stl"): os.remove(os.path.join(OUT_STL, f))
IMPR = {}
for ob in NODOS:
    nom = ob.name.replace("PETG_Carcasa_", "") + ".stl"
    IMPR[ob.name] = export_stl(ob, os.path.join(OUT_STL, nom))
    export_stl(ob, os.path.join(OUT_STL_MONT, nom), imprimir=False)     # misma pieza en posicion de montaje (referencia)
    bm = bmesh.new(); bm.from_mesh(ob.data); vol_petg += bm.calc_volume() * 1e9; bm.free()
n_bend = len(DOBLECES)
lista = ["CARCASA DEL MECANISMO v2 - Ovum2_4_inox  (carcasa_mecanismo_ovum2_4.py)", "",
         f"ENVOLVENTE inox 0.6, UNA pieza: desarrollo {W_FLAT:.1f} x {H_FLAT:.1f} mm, {n_bend} dobleces a 90 (todos hacia el mismo lado)",
         f"  agujeros: {sum(1 for g in AG if g[3] == 'rivnut')} x 5.0 (rivnut M3), {sum(1 for g in AG if g[3] == 'M5')} x 5.5 (M5), {sum(1 for g in AG if g[3] == 'M3')} x 3.4 (M3)",
         f"  caja terminada: {2 * XS:.0f} x {YF - YB:.0f} x {ZT - ZB:.0f} mm (x, y, z)", "",
         f"TAPA acrilico 4 mm: {2 * XS:.0f} x {YF - YB:.0f} mm, esquinas R3, {len(TAPA_PTS)} agujeros 3.4", "",
         f"PETG: marco fino de {len(NODOS)} piezas (8 nodos + 10 puentes), {vol_petg / 1000:.1f} cm3 en total (~{vol_petg / 1000 * 1.27:.0f} g macizo)"]
COMO_APOYA = {"_Inf": "base plana abajo", "_Sup": "boca abajo (cara de la tapa en la cama)", "_Vertical": "acostado sobre su cara lateral"}
for ob in NODOS:
    d = IMPR[ob.name]; como = next(v for k, v in COMO_APOYA.items() if k in ob.name)
    lista.append(f"  {ob.name.replace('PETG_Carcasa_', '')}.stl: {d[0]:.0f} x {d[1]:.0f} x {d[2]:.0f} mm en cama, {como}")
lista += ["", "IMPRESION (STL de esta carpeta ya orientados, en mm, apoyados en z=0; los de 'montaje/' estan en posicion de ensamble):",
          "  PETG, boquilla 0.4, capa 0.2, 4 perimetros (las paredes de los manguitos son de ~1.85 mm), relleno 30-40 % gyroid.",
          "  Soportes SOLO desde la cama (arbol/organicos): los nodos superiores apoyan en los dos manguitos y el cuerpo",
          "  queda 2 mm en el aire; los puentes apoyan en su cara redondeada (superelipse, casi plana): usar brim de 3-4 mm.",
          "  Izq y Der son piezas espejo: imprimir cada archivo una vez (no espejar en el laminador).",
          "  Agujeros M3 de 3.4 mm: si salen justos, pasar broca de 3.4. Probar primero 1 nodo + 1 puente (ajuste de manguito 0.15 mm).",
          "", "TORNILLERIA:",
          f"  {len(TAPA_PTS)} x tuerca remachable (rivnut) M3 cabeza plana en las pestanas superiores",
          f"  {sum(1 for t in TORN_MARCO if t[2] and t[1].z > 0.5)} x M3x16 cabeza boton (uniones de arriba: manguito + puente + acrilico -> rivnut)",
          f"  {sum(1 for t in TORN_MARCO if not t[2] and t[1].z > 0.5)} x M3x12 cabeza boton (esquinas y centros de arriba -> acrilico -> rivnut)",
          f"  {sum(1 for t in TORN_MARCO if t[2] and t[1].z < 0.5)} x M3x10 cabeza boton + tuerca por dentro (uniones laterales: manguito + puente + chapa)",
          f"  {sum(1 for t in TORN_MARCO if not t[2] and t[1].z < 0.5)} x M3x8 cabeza boton + tuerca por dentro (nodos inferiores y centros de puentes verticales)",
          f"  {len(M5_PTS)} x M5x10 + tuerca T 2020 (pestanas inferiores de los laterales)",
          "", "ARMADO: cortar y agujerear plano -> remachar rivnuts -> doblar pestanas -> doblar las 4 esquinas",
          "        -> presentar sobre el bastidor por arriba (pasa por encima de la canaleta) -> M5",
          "        -> nodos inferiores -> puentes inferiores y verticales (entran en los manguitos) -> tapa",
          "        -> nodos superiores + puentes superiores encajados en sus manguitos -> M3 de union y de tapa."]
with open(os.path.join(OUT_STL, "Carcasa_lista.txt"), "w", encoding="utf-8") as fh: fh.write("\n".join(lista) + "\n")
rep.update(desarrollo=[round(W_FLAT, 1), round(H_FLAT, 1)], contornos=len(LOOPS), dobleces=n_bend, petg_cm3=round(vol_petg / 1000, 1))

bpy.data.collections.remove(tmp)
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
print("INFORME", json.dumps(rep, ensure_ascii=False))
if SAVE:
    bak = os.path.join(ROOT, "Ovum2_4_inox_antes_carcasa.blend")
    if not os.path.exists(bak): shutil.copy2(bpy.data.filepath, bak)
    bpy.ops.wm.save_mainfile()
