"""
Ovum1_7: bastidor de mesa (soportes estructurales) + cubierta del mecanismo principal.

Uso (Blender en segundo plano):
  blender --background Ovum1_7.blend --python soportes_cubierta_ovum1_7.py            -> construye y revisa (no guarda)
  blender --background Ovum1_7.blend --python soportes_cubierta_ovum1_7.py -- save    -> construye, revisa y guarda

Todo lo generado vive en las colecciones "Soportes_Mesa" y "Cubierta_Mecanismo" y lleva la propiedad
"ovum17_gen"; al volver a correr el script se borra y se reconstruye. No modifica ninguna pieza existente.

Criterios:
  - La mesa es z = 0. Patas de caucho de 8 mm + perfil 2020 -> cara superior del bastidor en z = 0.028.
  - Perfil de aluminio 2020 (20 x 20 mm) para bastidor, postes y travesanos; piezas de apoyo en PETG.
  - Los postes se cortan a la altura real de cada pieza (se mide con rayos), asi siguen al modelo.
  - Los soportes de la canaleta quedan fuera de la zona del modulo de limpieza (y -0.29..-0.12).
  - La cubierta deja libre: la entrada de huevos por las varillas (ranura trasera) y la salida
    hacia el redireccionador y las bandejas (frente abierto). La tapa es removible (acrilico ahumado).
"""
import bpy, bmesh, json, math, sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
sc = bpy.context.scene
vl = bpy.context.view_layer
O = bpy.data.objects

# ------------------------------------------------------------------ utilidades
def coll(name):
    c = bpy.data.collections.get(name)
    if not c:
        c = bpy.data.collections.new(name); sc.collection.children.link(c)
    return c

def mat(name, col, metal=0.0, rough=0.5, alpha=1.0):
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*col, 1.0)
    b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        try: m.surface_render_method = 'BLENDED'
        except Exception: pass
    m.diffuse_color = (*col, alpha)
    return m

M_ALU = mat("Aluminio_2020", (0.78, 0.79, 0.81), 0.9, 0.35)
M_CAU = mat("Caucho_Patas", (0.03, 0.03, 0.03), 0.0, 0.9)
M_PETG = mat("PETG_Negro_Soporte", (0.06, 0.06, 0.07), 0.0, 0.45)
M_ACR = mat("Acrilico_Ahumado", (0.10, 0.11, 0.12), 0.0, 0.05, alpha=0.35)
M_ESC = mat("Acero_Escuadra", (0.55, 0.56, 0.58), 0.8, 0.4)

C_SOP = coll("Soportes_Mesa")
C_CUB = coll("Cubierta_Mecanismo")

# borrar lo generado antes (idempotente)
for o in [o for o in O if o.get("ovum17_gen")]:
    me = o.data; bpy.data.objects.remove(o, do_unlink=True)
    if me and me.users == 0: bpy.data.meshes.remove(me)

made = []
def new_obj(name, bm, material, col, rb=False):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(material)
    o = bpy.data.objects.new(name, me); col.objects.link(o); o["ovum17_gen"] = True
    if rb:
        if not sc.rigidbody_world: bpy.ops.rigidbody.world_add()
        rbw = sc.rigidbody_world
        if rbw.collection is None:
            rbw.collection = bpy.data.collections.new("RigidBodyWorld")
        rbw.collection.objects.link(o)
        r = o.rigid_body; r.type = 'PASSIVE'; r.collision_shape = 'MESH'; r.friction = 0.5
        r.use_margin = True; r.collision_margin = 0.0005
    made.append(o)
    return o

def box(x0, x1, y0, y1, z0, z1, bm=None):
    own = bm is None
    if own: bm = bmesh.new()
    g = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=g['verts'], vec=(x1 - x0, y1 - y0, z1 - z0))
    bmesh.ops.translate(bm, verts=g['verts'], vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return bm

def cyl(x, y, r, z0, z1, seg=24, bm=None):
    if bm is None: bm = bmesh.new()
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=z1 - z0)
    bmesh.ops.translate(bm, verts=g['verts'], vec=(x, y, (z0 + z1) / 2))
    return bm

def prism_xz(pts, y0, y1, bm=None):
    """prisma: poligono en el plano XZ extruido entre y0 e y1"""
    if bm is None: bm = bmesh.new()
    a = [bm.verts.new((x, y0, z)) for x, z in pts]
    b = [bm.verts.new((x, y1, z)) for x, z in pts]
    bm.faces.new(a); bm.faces.new(list(reversed(b)))
    n = len(pts)
    for i in range(n):
        bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm

def prism_yz(pts, x0, x1, bm=None):
    if bm is None: bm = bmesh.new()
    a = [bm.verts.new((x0, y, z)) for y, z in pts]
    b = [bm.verts.new((x1, y, z)) for y, z in pts]
    bm.faces.new(a); bm.faces.new(list(reversed(b)))
    n = len(pts)
    for i in range(n):
        bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm

# superficie real de las piezas (rayos verticales sobre las piezas visibles)
dg = bpy.context.evaluated_depsgraph_get()
VIS = {o.name for o in vl.objects if not o.hide_get() and not o.get("ovum17_gen")}
def surf(x, y, names, up=False, z_from=None):
    """z de la primera cara de 'names' encontrada bajando desde arriba (o subiendo desde abajo si up)"""
    d = Vector((0, 0, 1 if up else -1))
    org = Vector((x, y, z_from if z_from is not None else (0.0 if up else 1.0)))
    for _ in range(20):
        ok, loc, n, i, ob, m = sc.ray_cast(dg, org, d, distance=2.0)
        if not ok: return None
        if ob.name in names: return loc.z
        org = loc + d * 0.0003
    return None

warn = []
P = 0.020            # perfil 2020
H = P / 2
Z_FOOT = 0.008       # pata de caucho
Z_TOP = Z_FOOT + P   # cara superior del bastidor (0.028)

# ------------------------------------------------------------------ 1. bastidor de mesa
X_L = 0.200          # largueros en x = +-0.20
Y0, Y1 = -0.610, 0.610
bm = bmesh.new()
for sx in (-1, 1):
    box(sx * X_L - H, sx * X_L + H, Y0, Y1, Z_FOOT, Z_TOP, bm)
new_obj("Bastidor_Largueros_2020", bm, M_ALU, C_SOP)

Y_TRAV = {"canaleta_atras": -0.580, "canaleta_media": -0.360, "pedestal_atras": -0.098,
          "pedestal_frente": 0.014, "bandejas_atras": 0.100, "bandejas_centro": 0.330, "bandejas_frente": 0.560}
bm = bmesh.new()
for k, y in Y_TRAV.items():
    box(-X_L + H, X_L - H, y - H, y + H, Z_FOOT, Z_TOP, bm)
new_obj("Bastidor_Travesanos_2020", bm, M_ALU, C_SOP)

bm = bmesh.new()
for sx in (-1, 1):
    for y in (Y0 + 0.02, 0.0, Y1 - 0.02):
        cyl(sx * X_L, y, 0.015, 0.0, Z_FOOT, 24, bm)
new_obj("Patas_Caucho", bm, M_CAU, C_SOP)

# escuadras (angulos de acero) en las uniones larguero-travesano, por dentro
bm = bmesh.new()
for y in Y_TRAV.values():
    for sx in (-1, 1):
        xi = sx * (X_L - H)                 # cara interior del larguero
        for sy in (-1, 1):
            yy = y + sy * H                 # cara del travesano
            # placa horizontal triangular de 3 mm sobre el bastidor
            pts = [(xi, yy), (xi - sx * 0.018, yy), (xi, yy + sy * 0.018)]
            vs = [bm.verts.new((px, py, Z_TOP)) for px, py in pts] + [bm.verts.new((px, py, Z_TOP + 0.003)) for px, py in pts]
            for f in ((0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)):
                bm.faces.new([vs[i] for i in f])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
new_obj("Escuadras_Bastidor", bm, M_ESC, C_SOP)

def post(name, x, y, z_top, col=C_SOP, gussets=True):
    """poste 2020 vertical sobre el bastidor hasta z_top, con dos escuadras en la base"""
    bm = box(x - H, x + H, y - H, y + H, Z_TOP, z_top)
    if gussets and z_top - Z_TOP > 0.06:
        g = 0.025
        for sx in (-1, 1):
            xs = x + sx * H
            prism_xz([(xs, Z_TOP), (xs + sx * g, Z_TOP), (xs, Z_TOP + g)], y - 0.002, y + 0.002, bm)
    return new_obj(name, bm, M_ALU, col)

# ------------------------------------------------------------------ 2. canaleta de varillas
RAIL = O["Rieles_Canaleta"]
rw = [RAIL.matrix_world @ v.co for v in RAIL.data.vertices]
def rail_ends(yend):
    s = [w for w in rw if abs(w.y - yend) < 0.003]
    return min(w.z for w in s)
YB, YF = min(w.y for w in rw), max(w.y for w in rw)
ZB, ZF = rail_ends(YB), rail_ends(YF)
def rail_bottom(y): return ZF + (y - YF) * (ZB - ZF) / (YB - YF)
RX = 0.015; RR = 0.004            # centros de varilla en x = +-0.015, diametro 8 mm
for k in ("canaleta_atras", "canaleta_media"):
    y = Y_TRAV[k]
    zb = rail_bottom(y)
    z_post = zb - 0.012                                   # sillin de 12 mm bajo la varilla
    post("Poste_Canaleta_" + k.split("_")[1], 0.0, y, z_post)
    bm = box(-0.026, 0.026, y - 0.012, y + 0.012, z_post, zb)          # sillin PETG
    for sx in (-1, 1):                                                  # mejillas exteriores hasta el centro de varilla
        box(sx * (RX + RR + 0.0005), sx * (RX + RR + 0.0035), y - 0.012, y + 0.012, zb, zb + RR, bm)
    box(-(RX - RR - 0.0005), RX - RR - 0.0005, y - 0.012, y + 0.012, zb, zb + RR, bm)   # separador central
    new_obj("Sillin_Varillas_" + k.split("_")[1], bm, M_PETG, C_SOP, rb=True)

# ------------------------------------------------------------------ 3. pedestal del mecanismo principal
SP = {"Soporte principal"}
ped = {}
for tag, x, y in (("atras_izq", -0.045, -0.098), ("atras_der", 0.026, -0.098),
                  ("frente_izq", -0.024, 0.014), ("frente_der", 0.025, 0.014)):
    zs = surf(x, y, SP, up=True, z_from=0.03)
    if zs is None or zs > 0.11:
        warn.append(f"pedestal {tag}: sin placa base encima (z={zs})"); zs = 0.1014
    ped[tag] = zs
    post("Poste_Pedestal_" + tag, x, y, zs, gussets=False)

# ------------------------------------------------------------------ 4. bandejas
TR_UP = {"Bandeja 2", "Bandeja 3"}; TR_LO = {"Bandeja 1", "Bandeja 4"}
def pad(name, x, y, names, w=0.030):
    """calza PETG desde el bastidor hasta la cara inferior de la bandeja (sobre un travesano)"""
    z = surf(x, y, names)
    if z is None:
        warn.append(f"{name}: no hay bandeja en ({x}, {y})"); return
    if z - Z_TOP > 0.05:
        post(name, x, y, z - 0.004, gussets=False)       # poste 2020 + taco de 4 mm
        bm = box(x - 0.015, x + 0.015, y - 0.015, y + 0.015, z - 0.004, z)
        new_obj(name + "_Taco", bm, M_PETG, C_SOP)
    else:
        bm = box(x - w / 2, x + w / 2, y - H, y + H, Z_TOP, z)
        new_obj(name, bm, M_PETG, C_SOP)

# atras (y 0.10): postes bajo las bandejas superiores, calzas bajo las inferiores
for sx, side in ((-1, "izq"), (1, "der")):
    pad(f"Poste_Bandeja_Sup_{side}", sx * 0.060, Y_TRAV["bandejas_atras"], TR_UP)
    pad(f"Calza_Bandeja_Inf_atras_{side}", sx * 0.180, Y_TRAV["bandejas_atras"], TR_LO)
# centro (y 0.33): poste central por el hueco entre bandejas inferiores + travesano bajo las superiores
yc = Y_TRAV["bandejas_centro"]
z_up = min(z for z in (surf(sx * 0.10, yc, TR_UP) for sx in (-1, 1)) if z is not None)
z_tr0 = z_up - P
post("Poste_Central_Bandejas", 0.0, yc, z_tr0)
bm = box(-0.175, 0.175, yc - H, yc + H, z_tr0, z_up)
new_obj("Travesano_Bandejas_Superiores_2020", bm, M_ALU, C_SOP)
bm = bmesh.new()                                           # cartelas PETG poste-travesano
z_wall = max(w.z for nm in TR_LO for w in (O[nm].matrix_world @ v.co for v in O[nm].data.vertices) if abs(w.y - yc) < 0.06 and abs(w.x) < 0.03)
z_c0 = max(z_wall + 0.003, z_tr0 - 0.030)                  # por encima de las paredes internas de las bandejas inferiores
for sx in (-1, 1):
    prism_xz([(sx * H, z_tr0), (sx * (H + 0.040), z_tr0), (sx * H, z_c0)], yc - 0.003, yc + 0.003, bm)
new_obj("Cartelas_Travesano", bm, M_PETG, C_SOP)
for sx, side in ((-1, "izq"), (1, "der")):
    pad(f"Calza_Bandeja_Inf_centro_{side}", sx * 0.120, yc, TR_LO)
# frente (y 0.56): calzas bajo las bandejas inferiores
for sx, side in ((-1, "izq"), (1, "der")):
    for xx, t in ((0.050, "int"), (0.170, "ext")):
        pad(f"Calza_Bandeja_Inf_frente_{side}_{t}", sx * xx, Y_TRAV["bandejas_frente"], TR_LO)

# ------------------------------------------------------------------ 5. cubierta del mecanismo principal
CX0, CX1 = -0.085, 0.066          # envolvente en x (servo a la izquierda, placa de camara a la derecha)
CY0 = -0.145                      # pared trasera (las varillas entran por una ranura)
CY_F_SUP = -0.022                 # frente de la capota: antes de que empiecen las bandejas (y -0.018)
CY_F_INF = 0.036                  # frente de la carcasa inferior (bajo las bandejas, encierra el motor)
T = 0.003                         # pared de 3 mm
Z_PLACA = min(ped.values())       # cara inferior de la placa base
Z_INF1 = Z_PLACA - 0.001          # la carcasa inferior llega justo bajo la placa
Z_CAP0, Z_TAPA = Z_PLACA, 0.240   # capota: de la placa a la tapa (sobre lo mas alto: 0.227)
Z_DINTEL = 0.222                  # frente abierto hasta aqui (huevos sobre el redireccionador)
SLOT_X, SLOT_Z = 0.040, 0.150     # ranura trasera para varillas + huevos
CAM_X0, CAM_X1 = 0.0575, 0.0615   # placa lateral de camara existente (se respeta)
cam = O.get("Camara_Oscura_Tapa_Lateral")
if cam:
    cw = [cam.matrix_world @ Vector(c) for c in cam.bound_box]
    CAM_X0 = min(w.x for w in cw) - 0.0005; CAM_X1 = max(w.x for w in cw) + 0.0005
    CAM_Y0 = min(w.y for w in cw) - 0.0005

# carcasa inferior: caja abierta arriba, con rejilla de ventilacion al frente
bm = bmesh.new()
box(CX0, CX1, CY0, CY0 + T, Z_TOP, Z_INF1, bm)                 # atras
box(CX0, CX1, CY_F_INF - T, CY_F_INF, Z_TOP, Z_INF1, bm)       # frente (con ranuras abajo)
box(CX0, CX0 + T, CY0, CY_F_INF, Z_TOP, Z_INF1, bm)            # izquierda
box(CX1 - T, CX1, CY0, CY_F_INF, Z_TOP, Z_INF1, bm)            # derecha
new_obj("Carcasa_Inferior", bm, M_PETG, C_CUB)
bm = bmesh.new()                                               # rejilla (listones salientes en el frente)
for k in range(6):
    zz = Z_TOP + 0.012 + k * 0.009
    box(-0.050, 0.035, CY_F_INF, CY_F_INF + 0.0015, zz, zz + 0.004, bm)
new_obj("Carcasa_Inferior_Rejilla", bm, M_PETG, C_CUB)

# capota: laterales, trasera con ranura, dintel frontal
bm = bmesh.new()
box(CX0, CX0 + T, CY0, CY_F_SUP, Z_CAP0, Z_TAPA, bm)                    # lateral izquierdo
box(CX1 - T, CX1, CY0, CY_F_SUP, Z_CAP0, Z_TAPA, bm)                    # lateral derecho (fuera de la placa de camara)
box(CX0, -SLOT_X, CY0, CY0 + T, Z_CAP0, Z_TAPA, bm)                     # trasera izq.
box(SLOT_X, CX1, CY0, CY0 + T, Z_CAP0, Z_TAPA, bm)                      # trasera der.
box(-SLOT_X, SLOT_X, CY0, CY0 + T, Z_CAP0, SLOT_Z, bm)                  # trasera bajo la ranura
box(CX0, CAM_X0, CY_F_SUP - T, CY_F_SUP, Z_DINTEL, Z_TAPA, bm)          # dintel
box(CAM_X1, CX1, CY_F_SUP - T, CY_F_SUP, Z_DINTEL, Z_TAPA, bm)
new_obj("Cubierta_Capota", bm, M_PETG, C_CUB, rb=True)

# tapa removible de acrilico ahumado (con muesca para la placa de camara)
bm = bmesh.new()
box(CX0, CAM_X0, CY0, CY_F_SUP, Z_TAPA, Z_TAPA + T, bm)
box(CAM_X1, CX1, CY0, CY_F_SUP, Z_TAPA, Z_TAPA + T, bm)
if cam:
    box(CAM_X0, CAM_X1, CY0, CAM_Y0, Z_TAPA, Z_TAPA + T, bm)
new_obj("Cubierta_Tapa_Acrilico", bm, M_ACR, C_CUB, rb=True)
bm = bmesh.new()                                                       # tiradores
for xx in (-0.050, 0.020):
    box(xx - 0.010, xx + 0.010, -0.090, -0.078, Z_TAPA + T, Z_TAPA + T + 0.008, bm)
new_obj("Cubierta_Tapa_Tiradores", bm, M_PETG, C_CUB)

# ------------------------------------------------------------------ 6. revision de interferencias
def bvh(o):
    oe = o.evaluated_get(dg); me = oe.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); oe.to_mesh_clear(); bm.transform(o.matrix_world)
    t = BVHTree.FromBMesh(bm); bm.free(); return t
dg = bpy.context.evaluated_depsgraph_get()
others = [o for o in vl.objects if o.type == 'MESH' and not o.get("ovum17_gen") and not o.hide_get()
          and not o.name.startswith("Huevo")]
hidden = [o for o in vl.objects if o.type == 'MESH' and not o.get("ovum17_gen") and o.hide_get()
          and not o.name.startswith("Huevo")]
T_oth = {o.name: bvh(o) for o in others}
T_hid = {o.name: bvh(o) for o in hidden}
inter, inter_hidden = {}, {}
for m in made:
    tm = bvh(m)
    hit = [n for n, t in T_oth.items() if tm.overlap(t)]
    hh = [n for n, t in T_hid.items() if tm.overlap(t)]
    if hit: inter[m.name] = hit
    if hh: inter_hidden[m.name] = hh

def bbw(o):
    ws = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [[round(min(w[i] for w in ws), 3) for i in range(3)], [round(max(w[i] for w in ws), 3) for i in range(3)]]
report = {"creados": len(made), "objetos": {o.name: bbw(o) for o in made}, "avisos": warn,
          "interferencias_visibles": inter, "interferencias_ocultos": inter_hidden,
          "altura_maquina": round(max(max(bbw(o)[1][2] for o in made), 0), 3)}
if "save" in argv:
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
