"""Ovum Machine v1 - clasificadora de huevos por gravedad (Tilinka Hardworks).

Linea recta con riel inclinado 4 grados: los huevos ruedan solos de estacion en estacion.
  1. Carga: mesa en V, los huevos ruedan al centro y hacen fila sobre dos rieles.
  2. Escape: dos pasadores accionados por una leva (1 motor) sueltan UN huevo por ciclo.
  3. Limpieza: cama de 3 cepillos rotatorios + cepillo superior, todos empujan hacia adelante
     (frotan por deslizamiento sin frenar el flujo). Bandeja de polvo debajo.
  4. Inspeccion: el huevo cae en una cuna de caucho sobre una celda de carga (peso) dentro de
     una camara oscura; un LED de alta potencia lo ilumina desde abajo y una camara arriba toma
     la foto (ovoscopia: fecundado / sucio / fisurado). Luego la cuna se inclina y lo suelta.
  5. Distribucion: riel con 5 compuertas desviadoras (micro-servos), una por categoria de peso.
     Los rechazados (fecundados o defectuosos) siguen derecho hasta la caja final.

Uso: blender --background --factory-startup --python build_ovum_v1.py -- OUT.blend PREVIEW_PREFIX
"""
import bpy, bmesh, math, sys, json, random
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index("--")+1:]
OUT, PREV = argv[0], argv[1]

# ---------- escena limpia ----------
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
    for d in list(coll): coll.remove(d)
for c in list(bpy.data.collections): bpy.data.collections.remove(c)
sc = bpy.context.scene
sc.unit_settings.system = 'METRIC'; sc.unit_settings.length_unit = 'CENTIMETERS'
sc.render.fps = 24

# ---------- parametros ----------
ALPHA = math.radians(4.0)          # pendiente de la linea (los huevos ruedan solos)
TANA = math.tan(ALPHA)
X0, Z_RAIL0 = -0.30, 0.62          # inicio de la fila de carga y altura del eje de los rieles
RAIL_Y, RAIL_R = 0.015, 0.004      # rieles redondos inox d8 separados 30 mm
EGG_L, EGG_B = 0.057, 0.043; ER = EGG_B/2
EH = 0.0245                        # centro del huevo sobre el eje de los rieles
def zr(x): return Z_RAIL0 - TANA*(x - X0)
def ez(x): return zr(x) + EH

# estaciones (x a lo largo de la linea)
PIN_F, PIN_R = 0.075, 0.0285       # pasadores del escape (delantero / trasero)
XB0, XB1, XBT = 0.15, 0.31, 0.23   # modulo de limpieza y cepillo superior
XC = 0.50                          # cuna de inspeccion
XE = [0.66, 0.78, 0.90, 1.02, 1.14]   # salidas por categoria
SIDE = [1, -1, 1, -1, 1]              # lado de cada bandeja
CATS = ["Jumbo", "AAA", "AA", "A", "B"]
X_END = 1.32                       # fin del riel -> caja de rechazo

main = bpy.data.collections.new("Ovum_Machine_v1"); sc.collection.children.link(main)
def sub(n):
    c = bpy.data.collections.new(n); main.children.link(c); return c
cF, cA, cL, cI, cD, cE, cH = [sub(n) for n in ("1_Alimentacion", "2_Escape", "3_Limpieza", "4_Inspeccion",
                                               "5_Distribucion", "6_Estructura_Control", "Huevos")]
root = bpy.data.objects.new("Ovum_Raiz", None); main.objects.link(root); root.empty_display_size = 0.2

def mat(name, col, metal=0.0, rough=0.5, emit=None, alpha=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1); b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*col, 1); b.inputs["Emission Strength"].default_value = emit
    if alpha < 1: b.inputs["Alpha"].default_value = alpha
    m.diffuse_color = (*col, alpha); m.metallic = metal; m.roughness = rough
    return m
mat("Inox", (0.78, 0.79, 0.8), 1.0, 0.22)
mat("Aluminio_Perfil", (0.62, 0.64, 0.67), 0.9, 0.35)
mat("HDPE_Blanco", (0.93, 0.93, 0.92), 0.0, 0.4)
mat("Espuma_Gris", (0.45, 0.47, 0.5), 0.0, 0.9)
mat("Caucho_Negro", (0.02, 0.02, 0.02), 0.0, 0.8)
mat("Acento_Azul", (0.0, 0.32, 0.72), 0.0, 0.35)
mat("Negro_Mate", (0.03, 0.03, 0.035), 0.0, 0.9)
mat("Cerdas_Nylon", (0.95, 0.75, 0.15), 0.0, 0.6)
mat("Nucleo_Cepillo", (0.15, 0.15, 0.16), 0.0, 0.4)
mat("Motor_Gris", (0.25, 0.27, 0.3), 0.4, 0.4)
mat("Lente_Vidrio", (0.05, 0.08, 0.12), 0.0, 0.05)
mat("Pantalla_HMI", (0.1, 0.45, 0.65), 0.0, 0.2, emit=1.5)
led = mat("LED_Retroiluminacion", (1.0, 0.85, 0.6), 0.0, 0.3, emit=0.0)
mat("Celda_Carga", (0.7, 0.72, 0.75), 0.8, 0.3)
mat("Cascara_Huevo", (0.72, 0.42, 0.24), 0.0, 0.6)
M = bpy.data.materials

# ---------- utilidades de malla ----------
def mk(name, bm, coll, mats, loc=(0, 0, 0)):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(M[m])
    o = bpy.data.objects.new(name, me); coll.objects.link(o); o.parent = root; o.location = loc
    return o
def setmat(verts, mi):
    for f in {f for v in verts for f in v.link_faces}: f.material_index = mi
def prism(bm, pts, d, mi=0):
    vs = [bm.verts.new(p) for p in pts]
    f = bm.faces.new(vs)
    ex = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=nv, vec=d)
    setmat(vs + nv, mi); return vs + nv
def box(bm, c, s, mi=0, rot=None):
    g = bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, verts=g['verts'], vec=s)
    if rot is not None: bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=rot)
    bmesh.ops.translate(bm, verts=g['verts'], vec=c)
    setmat(g['verts'], mi); return g['verts']
def cyl(bm, p0, p1, r, seg=24, mi=0, r2=None):
    p0, p1 = Vector(p0), Vector(p1); d = p1 - p0
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=d.length)
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=q.to_matrix())
    bmesh.ops.translate(bm, verts=g['verts'], vec=(p0+p1)/2)
    setmat(g['verts'], mi); return g['verts']
def merge(bm, other):
    me = bpy.data.meshes.new("tmp"); other.to_mesh(me); other.free(); bm.from_mesh(me); bpy.data.meshes.remove(me)
RY_SLOPE = Matrix.Rotation(ALPHA, 3, 'Y')      # inclina una pieza con la linea

def brush(name, coll, r_core, r_tip, length, rows_dy=0.006, ntuft=20, axle=0.0):
    """cepillo cilindrico con eje en Y local (origen en el eje)"""
    bm = bmesh.new()
    cyl(bm, (0, -length/2, 0), (0, length/2, 0), r_core, 32, mi=0)
    if axle: cyl(bm, (0, -axle, 0), (0, axle, 0), 0.004, 12, mi=0)
    nrow = int(length/rows_dy)
    for i in range(nrow):
        y = -length/2 + rows_dy/2 + i*rows_dy
        for k in range(ntuft):
            a = 2*math.pi*(k + 0.5*(i % 2))/ntuft
            d = Vector((math.cos(a), 0, math.sin(a)))
            cyl(bm, d*(r_core-0.001) + Vector((0, y, 0)), d*r_tip + Vector((0, y, 0)), 0.0013, 5, mi=1, r2=0.0018)
    return mk(name, bm, coll, ["Nucleo_Cepillo", "Cerdas_Nylon"])

def key_rot(o, axis, f, val):
    o.rotation_euler[axis] = val; o.keyframe_insert("rotation_euler", index=axis, frame=f)
def key_loc(o, axis, f, val):
    o.location[axis] = val; o.keyframe_insert("location", index=axis, frame=f)
def fcurves_of(idb):
    ad = idb.animation_data; act = ad.action
    try:
        return [fc for ly in act.layers for st in ly.strips for fc in st.channelbag(ad.action_slot).fcurves]
    except AttributeError:
        return list(act.fcurves)
def linear_forever(o):
    for fc in fcurves_of(o):
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
        fc.extrapolation = 'LINEAR'

# ================= RIELES =================
bm = bmesh.new()
for xa, xb in ((X0, XB0), (XB1, XC-0.03), (XC+0.03, X_END)):
    for s in (-1, 1):
        cyl(bm, (xa, s*RAIL_Y, zr(xa)), (xb, s*RAIL_Y, zr(xb)), RAIL_R, 16)
# soportes de riel (silletas) cada ~25 cm
for x in (-0.25, -0.05, 0.12, 0.34, 0.56, 0.72, 0.96, 1.2, 1.3):
    box(bm, (x, 0, zr(x)-0.006), (0.012, 2*RAIL_Y+0.012, 0.006))
    box(bm, (x, 0, (zr(x)-0.009+0.40)/2), (0.012, 0.012, zr(x)-0.009-0.40))
mk("Rieles_Inox", bm, cE, ["Inox"])

# ================= 1. ALIMENTACION: mesa de carga en V =================
bm = bmesh.new()
TV = math.radians(9)
def vz(x, y): return zr(x) + RAIL_R - 0.002 + (abs(y)-0.03)*math.tan(TV)
xa, xb = X0-0.02, -0.01
for s in (-1, 1):
    pts = [Vector((xa, s*0.03, vz(xa, 0.03))), Vector((xb, s*0.03, vz(xb, 0.03))),
           Vector((xb, s*0.05, vz(xb, 0.05))), Vector((xa+0.06, s*0.22, vz(xa+0.06, 0.22))), Vector((xa, s*0.22, vz(xa, 0.22)))]
    prism(bm, pts, (0, 0, -0.004))
    # paredes del embudo
    prism(bm, [Vector((xa, s*0.22, vz(xa, 0.22))), Vector((xa+0.06, s*0.22, vz(xa+0.06, 0.22))), Vector((xb, s*0.05, vz(xb, 0.05))),
               Vector((xb, s*0.05, vz(xb, 0.05)+0.05)), Vector((xa+0.06, s*0.22, vz(xa+0.06, 0.22)+0.05)), Vector((xa, s*0.22, vz(xa, 0.22)+0.05))],
          (0, s*0.003, 0), mi=1)
prism(bm, [Vector((xa, -0.22, vz(xa, 0.22))), Vector((xa, 0.22, vz(xa, 0.22))), Vector((xa, 0.22, vz(xa, 0.22)+0.05)), Vector((xa, -0.22, vz(xa, 0.22)+0.05))], (-0.003, 0, 0), mi=1)
mk("Mesa_Carga_V", bm, cF, ["HDPE_Blanco", "Acento_Azul"])
# guias laterales de la fila (hasta el escape)
bm = bmesh.new()
for s in (-1, 1):
    for xa_, xb_ in ((-0.01, XB0-0.005),):
        p0 = Vector((xa_, s*0.033, zr(xa_)+0.012)); p1 = Vector((xb_, s*0.033, zr(xb_)+0.012))
        prism(bm, [p0, p1, p1+Vector((0, 0, 0.03)), p0+Vector((0, 0, 0.03))], (0, s*0.002, 0))
mk("Guias_Fila", bm, cF, ["Acento_Azul"])

# ================= 2. ESCAPE: 2 pasadores + leva (un solo motor) =================
def pin(name, x):
    bm = bmesh.new()
    cyl(bm, (0, 0, -0.06), (0, 0, 0), 0.003, 12)
    cyl(bm, (0, 0, -0.003), (0, 0, 0.001), 0.0045, 12, mi=1)
    o = mk(name, bm, cA, ["Inox", "Caucho_Negro"], (x, 0, 0))
    return o
PIN_UP = zr(PIN_F) + 0.014         # punta sobre el riel (bloquea)
pF = pin("Pasador_Delantero", PIN_F); pR = pin("Pasador_Trasero", PIN_R)
for p_, x in ((pF, PIN_F), (pR, PIN_R)):   # el origen queda en z=0: se anima la altura de la punta
    p_.location.z = PIN_UP
bm = bmesh.new()
xm = (PIN_F+PIN_R)/2; zc_ = zr(xm)-0.075
box(bm, (xm, -0.055, zc_), (0.05, 0.04, 0.04))                         # motorreductor de la leva
cyl(bm, (xm, -0.035, zc_), (xm, 0.0, zc_), 0.004, 12)
box(bm, (xm, 0.012, zc_+0.03), (0.07, 0.004, 0.09), mi=1)               # placa soporte
for x in (PIN_F, PIN_R):
    box(bm, (x, 0.0, zr(x)-0.03), (0.012, 0.012, 0.012), mi=1)          # bujes guia
mk("Escape_Motor", bm, cA, ["Motor_Gris", "Aluminio_Perfil"])
bm = bmesh.new()
pts = [Vector((0.016*math.cos(a)*(1.3 if math.cos(a) > 0.7 else 1.0), 0, 0.016*math.sin(a))) for a in [2*math.pi*k/24 for k in range(24)]]
prism(bm, pts, (0, 0.008, 0))
leva = mk("Leva_Escape", bm, cA, ["Acento_Azul"], (xm, -0.004, zc_))

# ================= 3. LIMPIEZA: cama de cepillos + cepillo superior =================
BED = [0.18, 0.23, 0.28]
bed_objs = []
for k, x in enumerate(BED):
    o = brush(f"Cepillo_Cama_{k+1}", cL, 0.008, 0.025, 0.09, ntuft=16, axle=0.075)
    o.location = (x, 0, zr(x) + RAIL_R - 0.025); bed_objs.append(o)
RB = 0.04
top_b = brush("Cepillo_Superior", cL, 0.016, RB, 0.10, ntuft=22, axle=0.075)
top_b.location = (XBT, 0, ez(XBT) + ER + RB - 0.004)
bm = bmesh.new()   # carcasa
ri, ro, yh = 0.05, 0.053, 0.072; n = 20
ring = [(math.cos(math.radians(-20+220*i/n)), math.sin(math.radians(-20+220*i/n))) for i in range(n+1)]
zc0 = top_b.location.z
def V(r, c, y): return bm.verts.new((XBT+r*c[0], y, zc0+r*c[1]))
oi = [V(ro, c, -yh) for c in ring]; oo = [V(ro, c, yh) for c in ring]
ii = [V(ri, c, -yh) for c in ring]; io = [V(ri, c, yh) for c in ring]
for i in range(n):
    bm.faces.new((oi[i], oi[i+1], oo[i+1], oo[i])); bm.faces.new((ii[i+1], ii[i], io[i], io[i+1]))
    bm.faces.new((oi[i+1], oi[i], ii[i], ii[i+1])); bm.faces.new((oo[i], oo[i+1], io[i+1], io[i]))
bm.faces.new((oi[0], oo[0], io[0], ii[0])); bm.faces.new((oi[-1], ii[-1], io[-1], oo[-1]))
for s in (-1, 1):   # placas laterales que sostienen todos los cepillos
    y = s*(yh+0.003)
    prism(bm, [Vector((XB0-0.01, y, zr(XB0)-0.05)), Vector((XB1+0.01, y, zr(XB1)-0.05)),
               Vector((XB1+0.01, y, zc0+0.02)), Vector((XB0-0.01, y, zc0+0.02))], (0, s*0.004, 0))
mk("Limpieza_Carcasa", bm, cL, ["Inox"])
bm = bmesh.new()   # bandeja de polvo + motor con transmision por correa (lado -Y)
box(bm, ((XB0+XB1)/2, 0, zr(0.23)-0.065), (XB1-XB0+0.03, 0.15, 0.004))
for s in (-1, 1): box(bm, ((XB0+XB1)/2, s*0.073, zr(0.23)-0.055), (XB1-XB0+0.03, 0.004, 0.02))
mk("Limpieza_Bandeja_Polvo", bm, cL, ["HDPE_Blanco"])
bm = bmesh.new()
box(bm, ((XB0+XB1)/2, -0.09, (zr(0.23)-0.05+zc0+0.02)/2), (XB1-XB0+0.04, 0.012, zc0+0.07-zr(0.23)), mi=0)   # cubre-correa
cyl(bm, (XBT, -0.096, zc0-0.07), (XBT, -0.17, zc0-0.07), 0.028, 32, mi=1)                                 # motor
box(bm, (XBT, -0.13, zc0-0.07+0.032), (0.03, 0.03, 0.016), mi=1)
mk("Limpieza_Motor_Correa", bm, cL, ["Acento_Azul", "Motor_Gris"])

# ================= 4. INSPECCION: camara oscura, LED inferior, camara, celda de carga =================
ZCRADLE = ez(XC-0.03) - 0.004                     # el huevo baja 4 mm a la cuna y se detiene
ROD_DX = 0.012; ROD_R = 0.004
rod_z = ZCRADLE - math.sqrt((ER+ROD_R)**2 - ROD_DX**2)
# cuna basculante (origen en la varilla delantera = pivote)
bm = bmesh.new()
for dx in (-ROD_DX, ROD_DX):
    cyl(bm, (dx-ROD_DX, -0.026, 0), (dx-ROD_DX, 0.026, 0), ROD_R, 16, mi=1)
for s in (-1, 1): box(bm, (-ROD_DX, s*0.028, -0.006), (0.034, 0.004, 0.016), mi=0)
cuna = mk("Cuna_Basculante", bm, cI, ["Aluminio_Perfil", "Caucho_Negro"], (XC+ROD_DX, 0, rod_z))
bm = bmesh.new()
box(bm, (XC+0.01, 0.0, rod_z-0.03), (0.08, 0.0127, 0.0127))           # celda de carga tipo barra
box(bm, (XC+0.055, 0.0, rod_z-0.05), (0.012, 0.012, 0.03))
mk("Celda_Carga_Pesaje", bm, cI, ["Celda_Carga"])
bm = bmesh.new()   # servo de basculamiento
box(bm, (XC+ROD_DX, 0.05, rod_z), (0.02, 0.02, 0.04))
cyl(bm, (XC+ROD_DX, 0.026, rod_z), (XC+ROD_DX, 0.04, rod_z), 0.003, 12)
mk("Servo_Cuna", bm, cI, ["Motor_Gris"])
bm = bmesh.new()   # LED de retroiluminacion con difusor
cyl(bm, (XC, 0, rod_z-0.022), (XC, 0, rod_z-0.016), 0.011, 32)
mk("LED_Retroiluminacion", bm, cI, ["LED_Retroiluminacion"])
bm = bmesh.new()
cyl(bm, (XC, 0, rod_z-0.03), (XC, 0, rod_z-0.022), 0.016, 32)          # disipador
for k in range(8): box(bm, (XC, 0, rod_z-0.04), (0.03, 0.0015, 0.016), rot=Matrix.Rotation(math.pi*k/8, 3, 'Z'))
mk("LED_Disipador", bm, cI, ["Negro_Mate"])
# camara oscura (frente -Y omitido para ver el interior; la tapa esta oculta en el outliner)
HX0, HX1, HZ0, HZ1, HY = XC-0.08, XC+0.08, rod_z-0.06, ZCRADLE+0.11, 0.075
bm = bmesh.new()
box(bm, ((HX0+HX1)/2, HY, (HZ0+HZ1)/2), (HX1-HX0, 0.003, HZ1-HZ0))      # fondo
box(bm, ((HX0+HX1)/2, 0, HZ1), (HX1-HX0, 2*HY, 0.003))                    # techo
box(bm, ((HX0+HX1)/2, 0, HZ0), (HX1-HX0, 2*HY, 0.003))                    # piso
for x in (HX0, HX1):   # paredes de entrada/salida con ranura para el paso del huevo
    zr_ = zr(x)
    box(bm, (x, 0, (zr_+0.06+HZ1)/2), (0.003, 2*HY, HZ1-zr_-0.06))
    box(bm, (x, 0, (HZ0+zr_-0.012)/2), (0.003, 2*HY, zr_-0.012-HZ0))
    for s in (-1, 1): box(bm, (x, s*(HY+0.04)/2, zr_+0.024), (0.003, HY-0.04, 0.072))
mk("Camara_Oscura", bm, cI, ["Negro_Mate"])
bm = bmesh.new()   # cortinas de caucho en la entrada y salida (bloquean la luz)
for x in (HX0-0.004, HX1+0.004):
    for k in range(5):
        y = -0.032 + 0.016*k
        box(bm, (x, y, zr(x)+0.036), (0.0015, 0.015, 0.048))
mk("Cortinas_Caucho", bm, cI, ["Caucho_Negro"])
bm = bmesh.new()
box(bm, ((HX0+HX1)/2, -HY, (HZ0+HZ1)/2), (HX1-HX0, 0.003, HZ1-HZ0))
tapa = mk("Camara_Oscura_Tapa_Frontal", bm, cI, ["Negro_Mate"])
tapa.hide_viewport = True; tapa.hide_render = True
bm = bmesh.new()   # camara (vista superior) con anillo y soporte
cyl(bm, (XC, 0, HZ1+0.002), (XC, 0, HZ1+0.035), 0.016, 32, mi=0)
cyl(bm, (XC, 0, HZ1-0.012), (XC, 0, HZ1+0.002), 0.009, 32, mi=1)
box(bm, (XC, 0, HZ1+0.045), (0.04, 0.04, 0.02), mi=0)
mk("Camara_Vision", bm, cI, ["Negro_Mate", "Lente_Vidrio"])

# ================= 5. DISTRIBUCION: guias, compuertas desviadoras, bandejas =================
GW = 0.034
bm = bmesh.new()   # guias laterales con huecos en cada salida
for s in (-1, 1):
    cuts = sorted([x for x, sd in zip(XE, SIDE) if sd == s])
    xs = [XC+0.09]
    for x in cuts: xs += [x-0.032, x+0.032]
    xs.append(X_END)
    for xa_, xb_ in zip(xs[0::2], xs[1::2]):
        p0 = Vector((xa_, s*GW, zr(xa_)+0.01)); p1 = Vector((xb_, s*GW, zr(xb_)+0.01))
        prism(bm, [p0, p1, p1+Vector((0, 0, 0.035)), p0+Vector((0, 0, 0.035))], (0, s*0.002, 0))
mk("Guias_Distribucion", bm, cD, ["Acento_Azul"])
flaps = []
FL = 0.075
for j, (x, s) in enumerate(zip(XE, SIDE)):
    bm = bmesh.new()
    box(bm, (-FL/2, 0, 0.0175), (FL, 0.003, 0.035), mi=0)
    cyl(bm, (0, 0, -0.012), (0, 0, 0.04), 0.004, 12, mi=1)
    o = mk(f"Compuerta_{CATS[j]}", bm, cD, ["HDPE_Blanco", "Inox"], (x+0.032, -s*(GW-0.004), zr(x+0.032)+0.01))
    o.rotation_euler = (0, 0, 0); flaps.append(o)
    bm = bmesh.new()
    box(bm, (x+0.032, -s*(GW+0.02), zr(x+0.032)-0.012), (0.024, 0.032, 0.022))
    mk(f"Servo_Compuerta_{CATS[j]}", bm, cD, ["Motor_Gris"])
# bandejas de recoleccion (HDPE con espuma), inclinadas hacia afuera
TY0, TY1 = 0.045, 0.40
TB = math.radians(7)
TRAY_W = 0.17
def tray_z(j, y):
    x = XE[j]; return zr(x) + RAIL_R - 0.014 - (abs(y)-TY0)*math.tan(TB)
for j, (x, s) in enumerate(zip(XE, SIDE)):
    bm = bmesh.new()
    xa_, xb_ = x-TRAY_W/2, x+TRAY_W/2
    pts = [Vector((xa_, s*TY0, tray_z(j, TY0))), Vector((xb_, s*TY0, tray_z(j, TY0))),
           Vector((xb_, s*TY1, tray_z(j, TY1))), Vector((xa_, s*TY1, tray_z(j, TY1)))]
    prism(bm, pts, (0, 0, -0.004), mi=0)
    prism(bm, [p + Vector((0, 0, 0.0035)) for p in pts], (0, 0, -0.0035), mi=1)          # espuma
    for xw in (xa_, xb_):
        prism(bm, [Vector((xw, s*TY0, tray_z(j, TY0))), Vector((xw, s*TY1, tray_z(j, TY1))),
                   Vector((xw, s*TY1, tray_z(j, TY1)+0.04)), Vector((xw, s*TY0, tray_z(j, TY0)+0.02))], (0.003, 0, 0), mi=0)
    prism(bm, [Vector((xa_, s*TY1, tray_z(j, TY1)-0.004)), Vector((xb_, s*TY1, tray_z(j, TY1)-0.004)),
               Vector((xb_, s*TY1, tray_z(j, TY1)+0.045)), Vector((xa_, s*TY1, tray_z(j, TY1)+0.045))], (0, s*0.012, 0), mi=2)
    mk(f"Bandeja_{CATS[j]}", bm, cD, ["HDPE_Blanco", "Espuma_Gris", "Caucho_Negro"])
    # etiqueta de categoria
    cu_ = bpy.data.curves.new(f"Etiqueta_{CATS[j]}", 'FONT'); cu_.body = CATS[j]; cu_.size = 0.028; cu_.extrude = 0.0006
    cu_.align_x = 'CENTER'; cu_.align_y = 'CENTER'; cu_.materials.append(M["Acento_Azul"])
    t_ = bpy.data.objects.new(f"Etiqueta_{CATS[j]}", cu_); cD.objects.link(t_); t_.parent = root
    t_.location = (x, s*(TY1+0.0125), tray_z(j, TY1)+0.025)
    t_.rotation_euler = (math.radians(90), 0, 0 if s < 0 else math.pi)
# caja de rechazo (fecundados / sucios / fisurados) al final del riel
BX0, BX1, BZ0 = X_END+0.01, X_END+0.17, zr(X_END)-0.16
bm = bmesh.new()
box(bm, ((BX0+BX1)/2, 0, BZ0), (BX1-BX0, 0.2, 0.006), mi=1)
for x in (BX0, BX1): box(bm, (x, 0, BZ0+0.06), (0.004, 0.2, 0.12))
for s in (-1, 1): box(bm, ((BX0+BX1)/2, s*0.1, BZ0+0.06), (BX1-BX0, 0.004, 0.12))
cyl(bm, (X_END-0.005, -0.03, zr(X_END)-0.01), (X_END-0.005, 0.03, zr(X_END)-0.01), 0.004, 12, mi=0)
mk("Caja_Rechazo", bm, cD, ["Acento_Azul", "Espuma_Gris"])
cu_ = bpy.data.curves.new("Etiqueta_Rechazo", 'FONT'); cu_.body = "RECHAZO"; cu_.size = 0.022; cu_.extrude = 0.0006
cu_.align_x = 'CENTER'; cu_.align_y = 'CENTER'; cu_.materials.append(M["HDPE_Blanco"])
t_ = bpy.data.objects.new("Etiqueta_Rechazo", cu_); cD.objects.link(t_); t_.parent = root
t_.location = ((BX0+BX1)/2, -0.103, BZ0+0.07); t_.rotation_euler = (math.radians(90), 0, 0)

# ================= 6. ESTRUCTURA (perfil de aluminio 40x40) Y CONTROL =================
P40 = 0.04; ZB = 0.38
bm = bmesh.new()
xs_frame = (X0-0.04, 1.50)
for s in (-1, 1):
    box(bm, ((xs_frame[0]+xs_frame[1])/2, s*0.30, ZB), (xs_frame[1]-xs_frame[0], P40, P40))            # largueros
    box(bm, ((xs_frame[0]+xs_frame[1])/2, s*0.30, 0.08), (xs_frame[1]-xs_frame[0], P40, P40))          # largueros bajos
for x in (xs_frame[0]+0.02, 0.43, 0.96, xs_frame[1]-0.02):
    box(bm, (x, 0, ZB), (P40, 0.60-P40, P40))                                                        # travesanos
    for s in (-1, 1):
        box(bm, (x, s*0.30, (0.04+ZB+P40/2)/2), (P40, P40, ZB+P40/2-0.04))                          # patas (sobre niveladores)
box(bm, ((xs_frame[0]+xs_frame[1])/2, 0, ZB), (xs_frame[1]-xs_frame[0], P40, P40))                   # viga central bajo el riel
for j, (x, s) in enumerate(zip(XE, SIDE)):                                                            # postes de bandejas
    for y in (0.1, 0.36):
        h0 = ZB+P40/2; h1 = tray_z(j, y) - 0.004
        box(bm, (x, s*y, (h0+h1)/2), (0.02, 0.02, h1-h0))
for x in (XB0+0.02, XB1-0.02):                                                                       # postes de limpieza
    for s in (-1, 1): box(bm, (x, s*0.077, (ZB+zr(x)-0.05)/2), (0.02, 0.02, zr(x)-0.05-ZB))
for x in (HX0+0.02, HX1-0.02):
    for s in (-1, 1): box(bm, (x, s*0.06, (ZB+HZ0)/2), (0.02, 0.02, HZ0-ZB))
for x in (-0.25, 0.0):
    for s in (-1, 1): box(bm, (x, s*0.15, (ZB+vz(x, 0.15)-0.004)/2), (0.02, 0.02, vz(x, 0.15)-0.004-ZB))
box(bm, ((BX0+BX1)/2, 0, (ZB+BZ0)/2), (0.03, 0.03, BZ0-ZB))
mk("Bastidor_Aluminio", bm, cE, ["Aluminio_Perfil"])
bm = bmesh.new()
for x in (xs_frame[0]+0.02, 0.43, 0.96, xs_frame[1]-0.02):
    for s in (-1, 1):
        cyl(bm, (x, s*0.30, 0.0), (x, s*0.30, 0.012), 0.022, 24, mi=1)
        cyl(bm, (x, s*0.30, 0.012), (x, s*0.30, 0.04), 0.006, 12, mi=0)
mk("Patas_Niveladoras", bm, cE, ["Inox", "Caucho_Negro"])
# tablero electrico + pantalla tactil (HMI) + Raspberry Pi / ESP32 / HX711 / drivers
bm = bmesh.new()
box(bm, (-0.15, -0.37, 0.27), (0.24, 0.1, 0.3), mi=0)
box(bm, (-0.15, -0.421, 0.33), (0.17, 0.003, 0.11), mi=1)
for k, x in enumerate((-0.22, -0.19, -0.16)):
    cyl(bm, (x, -0.42, 0.24), (x, -0.43, 0.24), 0.008, 16, mi=2 if k == 0 else 0)
box(bm, (-0.15, -0.33, 0.27), (0.04, 0.03, 0.04), mi=0)
mk("Tablero_Control_HMI", bm, cE, ["Motor_Gris", "Pantalla_HMI", "Caucho_Negro"])
cu_ = bpy.data.curves.new("Logo", 'FONT'); cu_.body = "OVUM  ·  Tilinka Hardworks"; cu_.size = 0.016; cu_.extrude = 0.0005
cu_.align_x = 'CENTER'; cu_.materials.append(M["HDPE_Blanco"])
t_ = bpy.data.objects.new("Logo_Tablero", cu_); cE.objects.link(t_); t_.parent = root
t_.location = (-0.15, -0.4215, 0.4); t_.rotation_euler = (math.radians(90), 0, 0)

# ================= HUEVO (malla con origen en su centro) =================
Lh, Bh, w = EGG_L, EGG_B, 0.0035
def rr(x):
    v = (Lh*Lh-4*x*x)/(Lh*Lh+8*w*x+4*w*w); return (Bh/2)*math.sqrt(max(v, 0))
bm = bmesh.new(); rings, segs = 36, 36
bot = bm.verts.new((0, 0, -Lh/2)); rows = []
for i in range(1, rings):
    t = i/rings; x = -Lh/2+Lh*(1-math.cos(math.pi*t))/2; r_ = rr(x)
    rows.append([bm.verts.new((r_*math.cos(2*math.pi*j/segs), r_*math.sin(2*math.pi*j/segs), x)) for j in range(segs)])
top = bm.verts.new((0, 0, Lh/2))
for j in range(segs):
    k = (j+1) % segs
    bm.faces.new((bot, rows[0][k], rows[0][j]))
    for a_, b_ in zip(rows, rows[1:]): bm.faces.new((a_[j], a_[k], b_[k], b_[j]))
    bm.faces.new((rows[-1][j], rows[-1][k], top))
meH = bpy.data.meshes.new("Huevo"); bm.to_mesh(meH); bm.free()
for p in meH.polygons: p.use_smooth = True
meH.materials.append(M["Cascara_Huevo"])

# ================= ANIMACION (ciclo de 2 s = 1800 huevos/h) =================
#  f0+0..3   : leva baja el pasador delantero y sube el trasero -> sale UN huevo
#  f0+3..12  : rueda por gravedad hasta la cama de cepillos
#  f0+12..26 : limpieza (los cepillos lo hacen girar rapido y lo llevan adelante)
#  f0+26..33 : rueda hasta la camara oscura y cae en la cuna (se detiene)
#  f0+35..42 : pesaje + LED encendido + foto (ovoscopia)
#  f0+44..47 : la cuna bascula y lo suelta; rueda hacia su salida
#  la compuerta de su categoria se abre antes de que llegue; los rechazados van a la caja final
TC, NC, K = 48, 16, 5
F = lambda c: 1 + c*TC
SPQ = EGG_B + 0.001                         # paso de la fila (huevos acostados, tocandose)
XQ0 = PIN_F - 0.003 - ER                    # primer huevo apoyado en el pasador delantero
random.seed(11)
def wrap(a): return (a + math.pi) % (2*math.pi) - math.pi
def classify(wg, fert):
    if fert: return -1
    for j, lim in enumerate((73, 67, 60, 53)):
        if wg >= lim: return j
    return 4
info = []
for c in range(NC):
    wg = round(random.gauss(63, 6.5), 1); fert = random.random() < 0.15
    info.append((wg, fert, classify(wg, fert)))
count = [0]*5; nrej = 0

def key_egg(o, f, loc, roll, yaw):
    o.location = loc; o.rotation_euler = (roll, math.pi/2, yaw)
    o.keyframe_insert("location", frame=f); o.keyframe_insert("rotation_euler", frame=f)
def key_vis(o, f, hidden):
    o.hide_viewport = hidden; o.hide_render = hidden
    o.keyframe_insert("hide_viewport", frame=f); o.keyframe_insert("hide_render", frame=f)
def lane(x): return Vector((x, 0, ez(x)))
YAW_LANE = math.pi/2                         # eje largo del huevo transversal a la linea

eggs = []
for i in range(NC + K + 1):
    o = bpy.data.objects.new(f"Huevo_{i+1:02d}", meH); cH.objects.link(o); o.parent = root
    o.rotation_mode = 'YXZ'                  # R = Rz(yaw) @ Rx(roll) @ Ry(90)
    eggs.append(o)
    spawn_c = max(0, i-K)
    k0 = i - spawn_c
    key_egg(o, F(spawn_c), lane(XQ0 - k0*SPQ), (XQ0 - k0*SPQ)/ER, YAW_LANE)
    if i > K:
        key_vis(o, 0, True); key_vis(o, F(spawn_c)+14, False)
    for c in range(spawn_c, min(i, NC)):
        k = i - c
        xa_, xb_ = XQ0 - k*SPQ, XQ0 - (k-1)*SPQ
        key_egg(o, F(c)+14, lane(xa_), xa_/ER, YAW_LANE)
        key_egg(o, F(c)+22, lane(xb_), xb_/ER, YAW_LANE)
    if i >= NC: continue
    c = i; f0 = F(c); wg, fert, cat = info[c]
    roll = XQ0/ER
    def go(f, x, extra=0.0, z=None):
        global roll
        p = lane(x) if z is None else Vector((x, 0, z))
        roll_new = x/ER + extra
        key_egg(o, f, p, roll_new, YAW_LANE)
    key_egg(o, f0+3, lane(XQ0), roll, YAW_LANE)
    go(f0+12, XB0+0.01)
    go(f0+26, XB1-0.005, extra=14.0)                    # los cepillos lo hacen girar de mas
    go(f0+31, XC-0.035, extra=14.0)
    go(f0+33, XC, extra=14.0, z=ZCRADLE)
    go(f0+44, XC, extra=14.0, z=ZCRADLE)
    base_roll = 14.0
    x_exit_lane = X_END if cat < 0 else XE[cat]
    v_frames = lambda dx: max(3, int(round(dx/0.12*5)))
    f_on = f0+47 + v_frames(x_exit_lane - (XC+0.04))
    go(f0+47, XC+0.04, extra=base_roll)
    if cat < 0:
        nrej += 1
        go(f_on, X_END, extra=base_roll)
        k_ = nrej-1
        bx = BX1 - 0.03 - (k_ % 3)*0.045; by = -0.05 + (k_ // 3 % 3)*0.05
        key_egg(o, f_on+6, Vector((bx, by, BZ0+0.0035+ER+0.004*(k_ // 9))), bx/ER+base_roll+2.0, YAW_LANE)
    else:
        j = cat; s = SIDE[j]
        go(f_on-2, XE[j]-0.012, extra=base_roll)
        # sale de lado: gira para rodar hacia afuera
        yaw_out = math.pi if s > 0 else 0.0
        r0 = (XE[j]-0.012)/ER + base_roll
        p_gap = Vector((XE[j]+0.004, s*0.05, tray_z(j, 0.05)+ER+0.002))
        key_egg(o, f_on+3, p_gap, r0, yaw_out)
        n_ = count[j]; count[j] += 1
        row, col = divmod(n_, 2)
        yy = TY1 - 0.012 - ER - 0.0005 - row*(EGG_B+0.001)
        end = Vector((XE[j] + (-0.033 if col == 0 else 0.033), s*yy, tray_z(j, yy)+ER+0.0035))
        dist = (end - p_gap).length
        key_egg(o, f_on+3+int(8+30*dist), end, r0 + dist/ER, yaw_out)
        # compuerta: se abre antes y se cierra despues
        fl = flaps[j]
        key_rot(fl, 2, f_on-12, 0.0); key_rot(fl, 2, f_on-6, -s*math.radians(40))
        key_rot(fl, 2, f_on+6, -s*math.radians(40)); key_rot(fl, 2, f_on+12, 0.0)
    # escape: pasador delantero baja y vuelve; trasero sube mientras tanto y luego deja avanzar la fila
    key_loc(pF, 2, f0, PIN_UP); key_loc(pF, 2, f0+3, PIN_UP-0.03)
    key_loc(pF, 2, f0+8, PIN_UP-0.03); key_loc(pF, 2, f0+11, PIN_UP)
    key_loc(pR, 2, f0, PIN_UP-0.03); key_loc(pR, 2, f0+3, PIN_UP)
    key_loc(pR, 2, f0+11, PIN_UP); key_loc(pR, 2, f0+14, PIN_UP-0.03)
    # cuna: bascula hacia adelante y vuelve
    key_rot(cuna, 1, f0+44, 0.0); key_rot(cuna, 1, f0+47, math.radians(28)); key_rot(cuna, 1, f0+52, 0.0)
    # LED de retroiluminacion: destello de ovoscopia
    socket = led.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    for f_, v_ in ((f0+34, 0.0), (f0+35, 40.0), (f0+42, 40.0), (f0+43, 0.0)):
        socket.default_value = v_; socket.keyframe_insert("default_value", frame=f_)

for o in eggs:
    for fc in fcurves_of(o):
        if fc.data_path.startswith("hide"):
            for kp in fc.keyframe_points: kp.interpolation = 'CONSTANT'
for o in [pF, pR] + flaps + [cuna]:
    if o.animation_data:
        for fc in fcurves_of(o):
            for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
# rotaciones continuas: leva (1 vuelta/ciclo), cepillos (empujan hacia adelante)
for o, axis, turns_per_s in ([(leva, 1, 0.5)] + [(b, 1, 4.0) for b in bed_objs] + [(top_b, 1, -5.0)]):
    key_rot(o, axis, 1, 0.0); key_rot(o, axis, 25, 2*math.pi*turns_per_s); linear_forever(o)
sc.frame_start, sc.frame_end = 1, F(NC) + 60

# ================= CAMARA Y LUZ =================
cam = bpy.data.objects.new("Camara", bpy.data.cameras.new("Camara")); sc.collection.objects.link(cam)
cam.data.lens = 35
def aim(o, loc, tgt):
    o.location = loc; o.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
CAM_MAIN = ((0.25, -1.75, 1.35), (0.55, 0.0, 0.45))
aim(cam, *CAM_MAIN); sc.camera = cam
sun = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", 'SUN')); sc.collection.objects.link(sun)
sun.rotation_euler = Euler((math.radians(35), math.radians(10), math.radians(25))); sun.data.energy = 3
sc.render.engine = 'BLENDER_EEVEE' if any(e.identifier == 'BLENDER_EEVEE' for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items) else sc.render.engine

# ================= MEDIDAS =================
bpy.context.view_layer.update()
mn = Vector((9, 9, 9)); mx = Vector((-9, -9, -9))
for ob in main.all_objects:
    if ob.type != 'MESH' or ob.name.startswith("Huevo") or ob.hide_render: continue
    for c in ob.bound_box:
        wv = ob.matrix_world @ Vector(c)
        mn = Vector(map(min, mn, wv)); mx = Vector(map(max, mx, wv))

# ================= VISTAS PREVIAS (workbench) =================
eng = sc.render.engine
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'MATERIAL'
sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
shots = {"general": (F(8)+20, CAM_MAIN[0], CAM_MAIN[1]),
         "limpieza": (F(6)+20, (0.05, -0.42, 0.85), (0.24, 0.0, 0.62)),
         "inspeccion": (F(6)+38, (0.45, -0.38, 0.72), (0.50, 0.0, 0.60)),
         "final": (F(NC)+50, (1.65, -1.2, 1.25), (0.85, 0.0, 0.45))}
for name, (fr, loc, tgt) in shots.items():
    sc.frame_set(fr); aim(cam, loc, tgt)
    sc.render.filepath = f"{PREV}_{name}.png"
    bpy.ops.render.render(write_still=True)
aim(cam, *CAM_MAIN)
sc.render.engine = eng
sc.frame_set(1)
sc.render.filepath = "//render_"
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("RESULT " + json.dumps({"medidas_cm": [round((mx-mn)[i]*100, 1) for i in range(3)],
                              "min_cm": [round(v*100, 1) for v in mn], "max_cm": [round(v*100, 1) for v in mx],
                              "frames": [sc.frame_start, sc.frame_end], "por_bandeja": dict(zip(CATS, count)),
                              "rechazados": nrej, "huevos": [list(x) for x in info], "saved": OUT}))
