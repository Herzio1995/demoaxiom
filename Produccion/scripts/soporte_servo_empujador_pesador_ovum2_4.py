"""
Ovum2_4_inox: soporte impreso (PETG) para "ServoEmpujadorPesador" (servo de la media luna del pesador),
atornillado a "BaseDelgadaMetal" (metal, soldada al bastidor).

Forma: una CAJA abierta arriba, toda por fuera del paso del huevo (x >= 35.9; el pesador llega a x 27.8):
  - Pie sobre la placa de BaseDelgadaMetal (z 60.9), 3 tornillos M4 verticales a rosca en la placa (4 mm).
  - Pared contra la cara exterior de la oreja derecha (x 35.8), 4 tornillos M4 horizontales a rosca en la oreja.
    La pared termina en z 106: debajo del acople/horn del eje (radio 13 alrededor de y -105.6, z 123.8).
  - Placa del servo perpendicular a su eje, con ventana para el cuerpo; la brida apoya en la cara exterior
    y se atornilla con 4 M4 + tuercas en alojamientos hexagonales por la cara interior.
  - Paredes trasera y delantera (cierran la caja) + 2 nervios exteriores a los lados de la brida.
  - Pollera que abraza el borde de la placa de BaseDelgadaMetal (x 54.4): ubica la pieza y toma el torque.
  Los tornillos de la oreja se alcanzan con llave Allen por los agujeros de acceso de la placa del servo
  (los de abajo) y por la ventana (los de arriba). Orden: soporte -> servo -> horn/acople.

El servo del modelo es una caja sin brida: la brida se supone tipo MG996R (SV_*). MEDIR el servo real y ajustar.

Salidas
  - Coleccion "SoporteServoEmpujadorPesador" con el soporte (PETG) y los tornillos de referencia.
  - Modificador Boolean "Taladros_SoporteServo" en BaseDelgadaMetal (agujeros de rosca M4 = broca 3.3).
  - Produccion/stl/SoporteServoEmpujadorPesador/SoporteServoEmpujadorPesador_PETG.stl
  - Copia de seguridad Ovum2_4_inox_antes_soporte_servo.blend (solo la primera vez).
Uso:  blender -b Ovum2_4_inox.blend --python Produccion/scripts/soporte_servo_empujador_pesador_ovum2_4.py -- [nosave]
"""
import bpy, bmesh, sys, os, math, json, shutil
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAVE = "nosave" not in argv
ROOT = os.path.dirname(bpy.data.filepath)
OUT_STL = os.path.join(ROOT, "Produccion", "stl", "SoporteServoEmpujadorPesador")
os.makedirs(OUT_STL, exist_ok=True)
O = bpy.data.objects
rep = {"avisos": []}
def aviso(s): rep["avisos"].append(s); print("AVISO:", s)

SERVO, BASE = "ServoEmpujadorPesador", "BaseDelgadaMetal"
COL = "SoporteServoEmpujadorPesador"

# ------------------------------------------------------------------ medidas del modelo (mm, mundo)
dg = bpy.context.evaluated_depsgraph_get()
def wverts(nm):
    o = O[nm]; oe = o.evaluated_get(dg); me = oe.to_mesh()
    vs = [(o.matrix_world @ v.co) * 1000.0 for v in me.vertices]; oe.to_mesh_clear(); return vs
sv = wverts(SERVO)
caja = [v for v in sv if v.x > 48.0 and v.z < 132.8]          # cuerpo (sin estrias del eje ni el saliente del cable)
SVX0 = min(v.x for v in caja); SVX1 = max(v.x for v in caja)  # tapa (lado del eje) / fondo
SVY0 = min(v.y for v in caja); SVY1 = max(v.y for v in caja)
SVZ0 = min(v.z for v in caja); SVZ1 = max(v.z for v in caja)
estria = [v for v in sv if v.x < SVX0 - 4.0]                 # solo la punta estriada (no el saliente de la tapa)
EJE_Y = (min(v.y for v in estria) + max(v.y for v in estria)) / 2; EJE_Z = (min(v.z for v in estria) + max(v.z for v in estria)) / 2
YC, ZC = (SVY0 + SVY1) / 2, (SVZ0 + SVZ1) / 2
rep["servo"] = {"x": [round(SVX0, 2), round(SVX1, 2)], "y": [round(SVY0, 2), round(SVY1, 2)],
                "z": [round(SVZ0, 2), round(SVZ1, 2)], "eje_yz": [round(EJE_Y, 2), round(EJE_Z, 2)]}

# BaseDelgadaMetal (medido con rayos en Ovum2_4_inox, ver informe)
X_OREJA = 35.8        # cara exterior de la oreja derecha (oreja x 31.8..35.8, y -116..-92.6, z 60.9..136.7)
Y_OREJA = (-116.0, -92.6)
Z_PLACA = 60.9        # cara superior de la placa (placa 4 mm: z 56.9..60.9)
X_BORDE = 54.4        # borde de la placa a la derecha, recto entre y -112 y -96
Y_PLACA_ATRAS = -112.0  # la placa (x > 36) empieza en y -112
Y_PEDESTAL = -82.0    # bloque elevado z 73 desde y -82 hacia adelante

# ------------------------------------------------------------------ parametros (mm)
HOLG = 0.1            # luz contra BaseDelgadaMetal
T_PIE, T_PARED, T_PLACA, T_LADO = 6.0, 5.0, 6.0, 5.0
# brida tipo MG996R (AJUSTAR): de la tapa del servo (cara del eje, sin estrias) a la cara de apoyo de la brida
SV_BRIDA = 10.0
SV_BRIDA_T = 2.5
SV_AG_L, SV_AG_W = 49.5, 10.0   # separacion de agujeros: a lo largo del servo (z) / a lo ancho (y)
SV_AG_D = 4.6                   # paso M4 (+-0.3 de ajuste)
TUERCA_AF, TUERCA_H = 7.3, 3.4  # alojamiento tuerca M4 por la cara interior
SV_HOLG = 0.6                   # ventana alrededor del cuerpo
R_HORN = 15.0                   # luz radial alrededor del eje (acople Cylinder.003 = R13) entre oreja y servo
M4_PASO, M4_ROSCA = 4.5, 3.3    # agujero pasante en PETG / broca para rosca M4 en el metal
ACCESO_D = 9.0                  # agujeros de acceso para la llave en la placa del servo
CABEZA_D = 7.0                  # cabeza M4 DIN912

XF = SVX0 + SV_BRIDA            # cara exterior de la placa = apoyo de la brida
XP0 = XF - T_PLACA              # cara interior de la placa
XW0, XW1 = X_OREJA + HOLG, X_OREJA + HOLG + T_PARED       # pared contra la oreja
YB1 = SVY0 - SV_HOLG - T_LADO - 1.0                       # cara exterior trasera (y minimo)
YB0 = YB1 + T_LADO
YF0 = SVY1 + 0.6; YF1 = YF0 + T_LADO                      # pared delantera (libra el cuerpo del servo)
Y_PIE1 = Y_PEDESTAL - 0.5
Z0 = Z_PLACA + 0.05
Z_PARED = EJE_Z - R_HORN - 2.0                            # alto de pared/lados (bajo el horn)
BRIDA = [(YC + a * SV_AG_W / 2, ZC + b * SV_AG_L / 2) for a in (-1, 1) for b in (-1, 1)]
Z_TOP = max(z for _, z in BRIDA) + TUERCA_AF / 2 + 3.5
TORN_PIE = [(XW1 + 6.7, Y_PLACA_ATRAS + 2.0 + 0.5), (XW1 + 6.7, YC + 5.6), (XW1 + 5.2, Y_PIE1 - 3.5)]
Z_OR_BAJO = Z0 + T_PIE + 7.0
TORN_OREJA = [(y, z) for y in (Y_PLACA_ATRAS + 1.0, YF0 - 3.5) for z in (Z_OR_BAJO, SVZ0 + 6.3)]

# ------------------------------------------------------------------ primitivas (bmesh, mm -> m)
def to_obj(name, bm, col):
    me = bpy.data.meshes.new(name); bmesh.ops.scale(bm, verts=bm.verts, vec=(0.001,) * 3)
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new(name, me); col.objects.link(ob); return ob
def box(bm, x0, x1, y0, y1, z0, z1):
    g = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=g['verts'], vec=(x1 - x0, y1 - y0, z1 - z0))
    bmesh.ops.translate(bm, verts=g['verts'], vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
def cyl(bm, c, axis, r, L, seg=32):
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=L)
    bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(Vector(axis)).to_matrix())
    bmesh.ops.translate(bm, verts=g['verts'], vec=Vector(c))
def prism_xz(bm, pts, y0, y1):
    """poligono en el plano xz extruido en y"""
    vb = [bm.verts.new((x, y0, z)) for x, z in pts]; vt = [bm.verts.new((x, y1, z)) for x, z in pts]
    n = len(pts)
    bm.faces.new(vb[::-1]); bm.faces.new(vt)
    for k in range(n): bm.faces.new((vb[k], vb[(k + 1) % n], vt[(k + 1) % n], vt[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

# ------------------------------------------------------------------ limpiar corridas anteriores
col = bpy.data.collections.get(COL)
if col is None:
    col = bpy.data.collections.new(COL); bpy.context.scene.collection.children.link(col)
for ob in list(col.objects): bpy.data.objects.remove(ob, do_unlink=True)
tmp = bpy.data.collections.new("_tmp_soporte_servo"); bpy.context.scene.collection.children.link(tmp)

# ------------------------------------------------------------------ solido
solidos = []
def S(name, f):
    bm = bmesh.new(); f(bm); solidos.append(to_obj(name, bm, tmp))
# pie (sobre la placa; atras de y -112 no hay placa, queda en el aire unido a la caja)
S("pie", lambda bm: box(bm, XW0, XF, YB1, Y_PIE1, Z0, Z0 + T_PIE))
# pared contra la oreja
S("pared_oreja", lambda bm: box(bm, XW0, XW1, YB1, YF1, Z0, Z_PARED))
# placa del servo
S("placa", lambda bm: box(bm, XP0, XF, YB1, YF1, Z0, Z_TOP))
# lados
S("lado_atras", lambda bm: box(bm, XW0, XF, YB1, YB0, Z0, Z_PARED))
S("lado_adelante", lambda bm: box(bm, XW0, XF, YF0, YF1, Z0, Z_PARED))
# nervios exteriores (a los lados de la brida), triangulares
NERV = [(XF - 0.5, Z0), (XF + 12.0, Z0), (XF + 3.0, Z_TOP), (XF - 0.5, Z_TOP)]
S("nervio_atras", lambda bm: prism_xz(bm, NERV, YB1, YB0))
S("nervio_adelante", lambda bm: prism_xz(bm, NERV, YF0, YF1))
# pollera contra el borde de la placa
S("pollera", lambda bm: box(bm, X_BORDE + HOLG, XF, Y_PLACA_ATRAS + 0.1, -96.1, Z_PLACA - 8.5, Z0 + 0.5))

# ------------------------------------------------------------------ cortes
cortes = []
def C(name, f):
    bm = bmesh.new(); f(bm); cortes.append(to_obj(name, bm, tmp))
C("ventana", lambda bm: box(bm, XP0 - 1, XF + 1, SVY0 - SV_HOLG, SVY1 + SV_HOLG, SVZ0 - SV_HOLG, SVZ1 + SV_HOLG))
# luz del horn / acople: cilindro alrededor del eje entre la oreja y la tapa del servo
C("luz_horn", lambda bm: cyl(bm, ((X_OREJA + SVX0) / 2, EJE_Y, EJE_Z), (1, 0, 0), R_HORN, SVX0 - X_OREJA + 0.2, 48))
for i, (y, z) in enumerate(BRIDA):
    C(f"brida_{i}", lambda bm, y=y, z=z: cyl(bm, (XF, y, z), (1, 0, 0), SV_AG_D / 2, 2 * T_PLACA + 2, 24))
    C(f"tuerca_{i}", lambda bm, y=y, z=z: cyl(bm, (XP0, y, z), (1, 0, 0), TUERCA_AF / math.sqrt(3), 2 * TUERCA_H, 6))
for i, (x, y) in enumerate(TORN_PIE):
    C(f"pie_{i}", lambda bm, x=x, y=y: cyl(bm, (x, y, Z0 + T_PIE / 2), (0, 0, 1), M4_PASO / 2, T_PIE + 2, 24))
for i, (y, z) in enumerate(TORN_OREJA):
    C(f"oreja_{i}", lambda bm, y=y, z=z: cyl(bm, ((XW0 + XW1) / 2, y, z), (1, 0, 0), M4_PASO / 2, T_PARED + 2, 24))
    if z < SVZ0 - SV_HOLG:      # bajo la ventana: agujero de acceso para la llave
        C(f"acceso_{i}", lambda bm, y=y, z=z: cyl(bm, ((XP0 + XF) / 2, y, z), (1, 0, 0), ACCESO_D / 2, T_PLACA + 2, 32))

# ------------------------------------------------------------------ booleanas (EXACT) y malla final
def boolean_merge(base, ops, op):
    for k, o in enumerate(ops):
        md = base.modifiers.new(f"b{k}", 'BOOLEAN'); md.operation = op; md.solver = 'EXACT'; md.object = o
    d = bpy.context.evaluated_depsgraph_get(); be = base.evaluated_get(d)
    me = bpy.data.meshes.new_from_object(be); base.modifiers.clear()
    old = base.data; base.data = me; bpy.data.meshes.remove(old)
base = solidos[0]
boolean_merge(base, solidos[1:], 'UNION')
boolean_merge(base, cortes, 'DIFFERENCE')
bm = bmesh.new(); bm.from_mesh(base.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), verts=bm.verts, edges=bm.edges)
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4 and any(len(e.link_faces) != 2 for e in f.edges)])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
nm_edges = sum(1 for e in bm.edges if not e.is_manifold)
bm.to_mesh(base.data); bm.free()
sop = bpy.data.objects.new(COL, base.data); col.objects.link(sop)
mat = None
for cand in ("PETG_Inox_Boca_BandejaCentral", "PETG_Esquinero_Der"):
    if cand in O and O[cand].data.materials: mat = O[cand].data.materials[0]; break
if mat: sop.data.materials.append(mat)
bpy.data.objects.remove(base, do_unlink=True)          # su malla queda en el soporte
for o in solidos[1:] + cortes:
    bpy.data.meshes.remove(o.data)
bpy.data.collections.remove(tmp)
rep["soporte"] = {"verts": len(sop.data.vertices), "aristas_no_manifold": nm_edges}
if nm_edges: aviso(f"soporte con {nm_edges} aristas no-manifold")

# ------------------------------------------------------------------ taladros en BaseDelgadaMetal + tornillos de referencia
bm = bmesh.new()
for x, y in TORN_PIE: cyl(bm, (x, y, Z_PLACA - 2.0), (0, 0, 1), M4_ROSCA / 2, 4.0 + 2.0, 24)
for y, z in TORN_OREJA: cyl(bm, (X_OREJA - 2.0, y, z), (1, 0, 0), M4_ROSCA / 2, 4.0 + 2.0, 24)
tal = to_obj("Taladros_M4_SoporteServo", bm, col); tal.hide_set(True); tal.hide_render = True; tal.display_type = 'WIRE'
bdm = O[BASE]
for md in [m for m in bdm.modifiers if m.name == "Taladros_SoporteServo"]: bdm.modifiers.remove(md)
md = bdm.modifiers.new("Taladros_SoporteServo", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.solver = 'EXACT'; md.object = tal

bm = bmesh.new()      # tornillos M4 (cabeza + vastago) solo para ver/medir largo
def tornillo(bm, cabeza_c, eje, L):
    e = Vector(eje); c = Vector(cabeza_c)
    cyl(bm, c - e * 2.0, eje, CABEZA_D / 2, 4.0, 24); cyl(bm, c + e * (L / 2), eje, 2.0, L, 16)
for x, y in TORN_PIE: tornillo(bm, (x, y, Z0 + T_PIE), (0, 0, -1), 10.0)          # M4x10: 6 PETG + 4 placa
for y, z in TORN_OREJA: tornillo(bm, (XW1, y, z), (-1, 0, 0), 8.0)                # M4x8: 4.9 PETG + 3.1 en la oreja
for y, z in BRIDA: tornillo(bm, (XF + SV_BRIDA_T, y, z), (-1, 0, 0), 12.0)        # M4x12 + tuerca
torn = to_obj("Tornillos_M4_SoporteServo", bm, col)

# ------------------------------------------------------------------ verificaciones
dg = bpy.context.evaluated_depsgraph_get()
def bvh(o, encoger=0.0):
    oe = o.evaluated_get(dg); b = bmesh.new(); b.from_mesh(oe.to_mesh()); oe.to_mesh_clear()
    b.transform(o.matrix_world); bmesh.ops.scale(b, verts=b.verts, vec=(1000,) * 3)
    if encoger:
        b.normal_update()
        for v in b.verts: v.co -= v.normal * encoger
    t = BVHTree.FromBMesh(b); b.free(); return t
T_SOP = bvh(sop, 0.02)
choques = []
for o in bpy.context.scene.objects:
    if o.type != 'MESH' or o.name in (sop.name, tal.name, torn.name) or o.hide_get(): continue
    if o.name.startswith("Molde_"): continue
    try:
        n = len(T_SOP.overlap(bvh(o)))
    except Exception as ex:
        n = -1
    if n: choques.append((o.name, n))
rep["choques_con_visibles"] = choques
for nm, n in choques: aviso(f"choque soporte <-> {nm}: {n} pares de triangulos")
# huevo / pesador: distancia minima en x
vs = [sop.matrix_world @ v.co * 1000 for v in sop.data.vertices]
rep["soporte_bbox"] = [[round(min(v[i] for v in vs), 2), round(max(v[i] for v in vs), 2)] for i in range(3)]
pes = wverts("PesadorSoporteSilicona")
rep["luz_al_pesador_x_mm"] = round(min(v.x for v in vs) - max(v.x for v in pes), 2)
# luz radial al eje entre la oreja y el servo
rad = [((v.y - EJE_Y) ** 2 + (v.z - EJE_Z) ** 2) ** 0.5 for v in vs if X_OREJA - 0.5 < v.x < SVX0]
rep["luz_radial_eje_mm"] = round(min(rad), 2) if rad else None
# los taladros caen en metal?
md.show_viewport = False; dg = bpy.context.evaluated_depsgraph_get()
T_BDM = bvh(bdm)          # sin los taladros
md.show_viewport = True; dg = bpy.context.evaluated_depsgraph_get()
def metal(p, d):
    h = T_BDM.ray_cast(Vector(p), Vector(d), 3.0); return h[0] is not None
rep["taladros_en_metal"] = [metal((x, y, Z_PLACA + 1), (0, 0, -1)) for x, y in TORN_PIE] + \
                           [metal((X_OREJA + 1, y, z), (-1, 0, 0)) for y, z in TORN_OREJA]
rep["parametros"] = {"XF_apoyo_brida": round(XF, 2), "placa_x": [round(XP0, 2), round(XF, 2)], "Z_pared": round(Z_PARED, 2),
                     "Z_top": round(Z_TOP, 2), "torn_pie_xy": [[round(a, 1), round(b, 1)] for a, b in TORN_PIE],
                     "torn_oreja_yz": [[round(a, 1), round(b, 1)] for a, b in TORN_OREJA],
                     "brida_yz": [[round(a, 2), round(b, 2)] for a, b in BRIDA]}

# ------------------------------------------------------------------ STL + guardar
for o in bpy.context.view_layer.objects: o.select_set(False)
sop.select_set(True); bpy.context.view_layer.objects.active = sop
stl = os.path.join(OUT_STL, "SoporteServoEmpujadorPesador_PETG.stl")
bpy.ops.wm.stl_export(filepath=stl, export_selected_objects=True, global_scale=1000.0, apply_modifiers=True)
rep["stl"] = stl
if SAVE:
    bak = os.path.join(ROOT, "Ovum2_4_inox_antes_soporte_servo.blend")
    if not os.path.exists(bak): shutil.copy2(bpy.data.filepath, bak)
    bpy.ops.wm.save_mainfile()
    rep["guardado"] = bpy.data.filepath
print("REPORTE " + json.dumps(rep, ensure_ascii=False, indent=1))
